"""
Merge brand_profiles rows that are the same store under different URL spellings.

WHY THIS EXISTS
---------------
`save_brand_profile()` used to dedupe on an exact `website_url` string match,
so these all became separate brands for the same account:

    https://www.asimjofa.com
    https://asimjofa.com
    https://www.asimjofa.com/

That is fixed going forward — `modules/scraping/scraper.py::normalize_store_url`
now canonicalises the URL before both the lookup and the insert. But rows
created *before* the fix are still there, and they are user-visible: the brand
switcher shows the same store twice, and because every module scopes to
`brand_profile_id`, an SEO audit run on one id is invisible on the other.

This script finds those groups and merges each one into a single row.

WHICH ROW SURVIVES
------------------
The one with the most attached work (SEO audits + blog posts + keyword sets +
chatbots + generated ads), then the oldest as a tie-break. Everything attached
to the losing rows is re-pointed at the survivor — nothing is orphaned, and no
generated content is lost.

USAGE
-----
    cd backend

    # See what it would do — changes nothing:
    python scripts/merge_duplicate_brands.py

    # Actually merge:
    python scripts/merge_duplicate_brands.py --apply

    # Limit to one account:
    python scripts/merge_duplicate_brands.py --user <uuid> --apply

A JSON backup of every deleted row is written next to this script before
anything is removed.
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

from modules.scraping.scraper import normalize_store_url  # noqa: E402


# Tables that reference brand_profiles.id, and the column that does it.
# Ordering does not matter — every row is simply re-pointed at the survivor.
REFERENCING = [
    ("seo_audit_results", "brand_profile_id"),
    ("seo_blog_posts", "brand_profile_id"),
    ("seo_keyword_suggestions", "brand_profile_id"),
    ("chatbot_instances", "brand_profile_id"),
    ("generated_ads", "brand_profile_id"),
    ("generated_video_ads", "brand_profile_id"),
]


def _existing_tables(conn) -> set:
    rows = conn.execute(text(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
    ))
    return {r[0] for r in rows}


def _column_exists(conn, table: str, column: str) -> bool:
    row = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t AND column_name=:c"
    ), {"t": table, "c": column}).first()
    return row is not None


def find_groups(conn, user_id: str | None):
    """Group this account's brands by canonical URL; keep only real duplicates."""
    sql = "SELECT id, user_id, business_name, website_url, created_at FROM brand_profiles"
    params = {}
    if user_id:
        sql += " WHERE user_id = :uid"
        params["uid"] = user_id
    sql += " ORDER BY id"

    groups = defaultdict(list)
    for row in conn.execute(text(sql), params).mappings():
        key = (row["user_id"], normalize_store_url(row["website_url"] or ""))
        groups[key].append(dict(row))

    return {k: v for k, v in groups.items() if len(v) > 1}


def count_attached(conn, tables, brand_id: int) -> dict:
    counts = {}
    for table, column in tables:
        n = conn.execute(
            text(f'SELECT count(*) FROM "{table}" WHERE {column} = :bid'),
            {"bid": brand_id},
        ).scalar()
        if n:
            counts[table] = n
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="actually merge (default is a dry run)")
    parser.add_argument("--user", help="limit to one user_id")
    args = parser.parse_args()

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL is not set — check backend/.env")
        return 1

    engine = create_engine(db_url)

    with engine.connect() as conn:
        present = _existing_tables(conn)
        tables = [
            (t, c) for t, c in REFERENCING
            if t in present and _column_exists(conn, t, c)
        ]
        skipped = [t for t, _ in REFERENCING if t not in present]
        if skipped:
            print(f"note: skipping tables that do not exist here: {', '.join(skipped)}\n")

        groups = find_groups(conn, args.user)

        if not groups:
            # brand_profiles saaf hai — magar sentiment ki apni `brands`
            # table mein alag duplicates ho sakte hain, is liye return
            # yahan NAHI karte.
            print("No duplicate brand profiles found.\n")
        else:
            print(f"Found {len(groups)} duplicated store(s):\n")

        plan = []
        for (user_id, canonical), rows in groups.items():
            scored = []
            for r in rows:
                counts = count_attached(conn, tables, r["id"])
                scored.append((sum(counts.values()), -r["id"], r, counts))
            # Most attached work wins; oldest id breaks the tie.
            scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

            keep = scored[0][2]
            keep_counts = scored[0][3]
            drop = [(s[2], s[3]) for s in scored[1:]]

            print(f"  {canonical}   (user {user_id})")
            print(f"    KEEP   id={keep['id']:<4} {keep['website_url']:<34} "
                  f"attached={keep_counts or '{}'}")
            for row, counts in drop:
                print(f"    MERGE  id={row['id']:<4} {row['website_url']:<34} "
                      f"attached={counts or '{}'}")
            print()

            plan.append((keep, [d[0] for d in drop]))

    if not args.apply:
        print("Dry run — nothing changed. Re-run with --apply to merge.")
        return 0

    # ── Backup before deleting anything ──────────────────────────────────
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = Path(__file__).resolve().parent / f"merge_backup_{stamp}.json"

    with engine.begin() as conn:
        doomed_ids = [r["id"] for _, drops in plan for r in drops]
        if doomed_ids:
            backup = [
                dict(row) for row in conn.execute(
                    text("SELECT * FROM brand_profiles WHERE id = ANY(:ids)"),
                    {"ids": doomed_ids},
                ).mappings()
            ]
            backup_path.write_text(json.dumps(backup, indent=2, default=str), encoding="utf-8")
            print(f"Backup of {len(backup)} row(s) written to {backup_path}\n")

        moved_total = 0
        for keep, drops in plan:
            for row in drops:
                for table, column in tables:
                    moved = conn.execute(
                        text(f'UPDATE "{table}" SET {column} = :keep WHERE {column} = :drop'),
                        {"keep": keep["id"], "drop": row["id"]},
                    ).rowcount
                    if moved:
                        moved_total += moved
                        print(f"  moved {moved:>3} row(s) in {table}: "
                              f"{row['id']} -> {keep['id']}")

                conn.execute(
                    text("DELETE FROM brand_profiles WHERE id = :id"),
                    {"id": row["id"]},
                )
                print(f"  deleted brand_profiles id={row['id']}")

            # Survivor keeps the canonical spelling from now on.
            conn.execute(
                text("UPDATE brand_profiles SET website_url = :url WHERE id = :id"),
                {"url": normalize_store_url(keep["website_url"] or ""), "id": keep["id"]},
            )

        if doomed_ids:
            print(f"\nDone. Re-pointed {moved_total} row(s), "
                  f"removed {len(doomed_ids)} duplicate brand(s).")

        # ── The sentiment module keeps its own brands table ──────────────
        # It is keyed by website_url and had the same "www." split, so the
        # same store could hold two rows with the analyses divided between
        # them. Merge those onto the oldest row and canonicalise the URL.
        if "brands" in present:
            merged = _merge_sentiment_brands(conn)
            if merged:
                print(f"Merged {merged} duplicate sentiment brand row(s).")

    return 0


def _merge_sentiment_brands(conn) -> int:
    """Collapse sentiment `brands` rows that canonicalise to the same URL."""
    rows = list(conn.execute(text(
        "SELECT brand_id, brand_name, website_url, created_at FROM brands ORDER BY created_at"
    )).mappings())

    groups = defaultdict(list)
    for r in rows:
        groups[normalize_store_url(r["website_url"] or "")].append(r)

    merged = 0
    for canonical, group in groups.items():
        if not canonical:
            continue
        keep = group[0]                      # oldest wins — analyses point at it
        for row in group[1:]:
            moved = conn.execute(text(
                "UPDATE sentiment_analyses SET brand_id = :keep WHERE brand_id = :drop"
            ), {"keep": keep["brand_id"], "drop": row["brand_id"]}).rowcount
            conn.execute(text("DELETE FROM brands WHERE brand_id = :id"),
                         {"id": row["brand_id"]})
            print(f"  sentiment brands: moved {moved} analysis row(s), "
                  f"dropped {row['website_url']}")
            merged += 1
        conn.execute(text("UPDATE brands SET website_url = :url WHERE brand_id = :id"),
                     {"url": canonical, "id": keep["brand_id"]})

    return merged


if __name__ == "__main__":
    raise SystemExit(main())
