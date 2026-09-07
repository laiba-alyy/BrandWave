"""
One-time cleanup — un users ka data hatata hai jo Supabase se ja chuke hain.

    python scripts/cleanup_orphaned_data.py                 # dry run (default)
    python scripts/cleanup_orphaned_data.py --apply         # asli deletion
    python scripts/cleanup_orphaned_data.py --apply --sentinel test_user_123
    python scripts/cleanup_orphaned_data.py --apply --prune-namespaces

── Safety usool (ye script data uda sakti hai, is liye padho) ───────────────

1. DRY RUN default hai. `--apply` ke baghair kuch delete nahi hota.

2. Supabase lookup fail ho to script MAR jati hai, aage nahi barhti.
   Ye sabse ahem guard hai: agar network/API error ko "user nahi mila" samajh
   liya jaye to script HAR user ko orphan samajh kar poora database uda degi.
   Is liye lookup ka fail hona = abort, na ke "koi user maujood nahi".

3. Sirf wo user_id orphan mana jata hai jo VALID UUID ho aur Supabase auth
   mein maujood na ho. `test_user_123` / `anonymous` jaise ids kabhi accounts
   the hi nahi — wo alag "sentinel" bucket mein jate hain.

   Sentinels ek jaise NAHI hote, is liye unhe NAAM le kar delete karna parta
   hai (`--sentinel test_user_123`). Misal ke tor par `anonymous` koi purana
   kachra nahi — AIAssistantWidget aaj bhi har logged-out visitor ki chat usi
   id par likhta hai. `--include-sentinels` sab ko ek saath uda deta hai, is
   liye usay sirf tab use karo jab har sentinel dekh liya ho.

4. Delete se pehle sab kuch ek JSON backup file mein likha jata hai.

5. Pinecone namespaces sirf tab hatti hain jab unke bot_id ki koi
   chatbot_instances row na bache (`--prune-namespaces`).

6. TODO — sentiment tables (`brands`, `sentiment_analyses`, `review_posts`)
   is script ke dayre se BAHAR hain, kyunke un mein user_id hai hi nahi.
   Tafseel aur do mumkin hal: modules/account_deletion.py ka TODO block.
   Jab tak ownership add na ho, ye script unhe chhuti bhi nahi aur unke bare
   mein koi da'wa bhi nahi karti.
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone

# scripts/ se chalane par backend/ import path mein chahiye
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from sqlalchemy import text

from database.connection import SessionLocal
from modules.account_deletion import _supabase_config, delete_user_data

# Har table jahan user_id aata hai — orphan candidates isi union se milte hain.
USER_ID_TABLES = [
    "brand_profiles",
    "seo_audit_results",
    "seo_blog_posts",
    "seo_keyword_suggestions",
    "generated_ads",
    "chatbot_instances",
    "assistant_chat_sessions",
    "assistant_chat_messages",
]


def is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def fetch_supabase_user_ids() -> set:
    """
    Supabase ke SAARE auth user ids.

    Koi bhi gharbar (HTTP error, network, missing key) par exception —
    kabhi khali set nahi. Khali set lautana matlab har user ko orphan
    declare kar dena.
    """
    url, key = _supabase_config()
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}

    ids, page = set(), 1
    while True:
        res = httpx.get(
            f"{url}/auth/v1/admin/users",
            headers=headers,
            params={"page": page, "per_page": 200},
            timeout=30,
        )
        if res.status_code != 200:
            raise RuntimeError(
                f"Supabase user list failed (HTTP {res.status_code}): {res.text[:200]}"
            )
        users = res.json().get("users", [])
        if not users:
            break
        ids.update(u["id"] for u in users)
        if len(users) < 200:
            break
        page += 1

    if not ids:
        raise RuntimeError("Supabase returned zero users — refusing to treat everyone as orphaned.")
    return ids


def collect_neon_user_ids(db) -> dict:
    counts = {}
    for table in USER_ID_TABLES:
        for uid, n in db.execute(
            text(f'SELECT user_id, count(*) FROM "{table}" GROUP BY user_id')
        ).fetchall():
            if uid is None:
                continue
            counts.setdefault(uid, {})[table] = n
    return counts


def orphaned_namespaces(db) -> list:
    """Pinecone namespaces jinke peeche koi live chatbot row nahi bachi."""
    from modules.chatbot_automation.pinecone_service import index

    stats = index.describe_index_stats()
    live = {r[0] for r in db.execute(text("SELECT bot_id FROM chatbot_instances")).fetchall()}
    return [
        (name, ns.get("vector_count", 0))
        for name, ns in (stats.namespaces or {}).items()
        if name not in live
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually delete (default: dry run)")
    ap.add_argument(
        "--include-sentinels",
        action="store_true",
        help="delete EVERY non-account id (blunt — prefer --sentinel)",
    )
    ap.add_argument(
        "--sentinel",
        action="append",
        default=[],
        metavar="ID",
        help="delete this specific non-account id (repeatable), e.g. test_user_123",
    )
    ap.add_argument(
        "--prune-namespaces",
        action="store_true",
        help="also delete Pinecone namespaces with no chatbot row",
    )
    args = ap.parse_args()

    mode = "APPLY (destructive)" if args.apply else "DRY RUN"
    print(f"=== Orphaned data cleanup — {mode} ===\n")

    print("Fetching Supabase auth users...")
    supabase_ids = fetch_supabase_user_ids()
    print(f"  {len(supabase_ids)} auth users found\n")

    db = SessionLocal()
    neon = collect_neon_user_ids(db)

    active, orphaned, sentinels = {}, {}, {}
    for uid, tables in neon.items():
        if not is_uuid(uid):
            sentinels[uid] = tables
        elif uid in supabase_ids:
            active[uid] = tables
        else:
            orphaned[uid] = tables

    print(f"ACTIVE users with data      : {len(active)}")
    for uid, t in active.items():
        print(f"    KEEP    {uid}  {sum(t.values())} rows")
    print(f"\nORPHANED users (deleted)    : {len(orphaned)}")
    for uid, t in orphaned.items():
        print(f"    DELETE  {uid}  {sum(t.values())} rows")
    print(f"\nSENTINEL ids (never accounts): {len(sentinels)}")
    for uid, t in sentinels.items():
        chosen = args.include_sentinels or uid in args.sentinel
        flag = "DELETE" if chosen else "SKIP  "
        print(f"    {flag}  {uid!r}  {sum(t.values())} rows  {t}")

    ns = orphaned_namespaces(db)
    print(f"\nORPHANED Pinecone namespaces: {len(ns)}")
    for name, count in ns:
        flag = "DELETE" if args.prune_namespaces else "SKIP  "
        print(f"    {flag}  {name!r}  {count} vectors")

    targets = dict(orphaned)
    for uid, tables in sentinels.items():
        if args.include_sentinels or uid in args.sentinel:
            targets[uid] = tables

    unknown = [s for s in args.sentinel if s not in sentinels]
    if unknown:
        # Typo par chup rehna khatarnak hai — user samjhega delete ho gaya.
        print(f"\n  WARNING: --sentinel id(s) not found in the database: {unknown}")

    if not targets and not (args.prune_namespaces and ns):
        print("\nNothing to clean up.")
        db.close()
        return

    # ── backup ───────────────────────────────────────────────────────────
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"cleanup_backup_{stamp}.json")
    backup = {"generated_at": stamp, "users": {}}
    for uid in targets:
        rows = {}
        for table in USER_ID_TABLES:
            rows[table] = [
                dict(r) for r in db.execute(
                    text(f'SELECT * FROM "{table}" WHERE user_id = :u'), {"u": uid}
                ).mappings().all()
            ]
        backup["users"][uid] = rows
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(backup, f, indent=2, default=str)
    print(f"\nBackup written: {backup_path}")

    # ── delete ───────────────────────────────────────────────────────────
    print("\n--- per-user cascade ---")
    for uid in targets:
        report = delete_user_data(uid, db, dry_run=not args.apply)
        print(f"  {uid}: {report['total_rows']} rows "
              f"{'deleted' if args.apply else 'would be deleted'}")

    if args.prune_namespaces:
        from modules.chatbot_automation.pinecone_service import delete_bot_data

        print("\n--- Pinecone namespaces ---")
        for name, count in ns:
            if args.apply:
                try:
                    delete_bot_data(name)
                    print(f"  {name!r}: deleted ({count} vectors)")
                except Exception as e:
                    print(f"  {name!r}: FAILED — {e}")
            else:
                print(f"  {name!r}: would delete ({count} vectors)")

    db.close()
    print("\nDone." if args.apply else "\nDry run complete — nothing was deleted.")


if __name__ == "__main__":
    main()
