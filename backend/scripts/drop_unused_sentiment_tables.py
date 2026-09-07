"""
Drop six unused tables that a legacy script created as an import side effect.

WHAT HAPPENED
-------------
`modules/sentiment/create_all_tables.py` ran its `CREATE TABLE` script at module
top level, so merely *importing* it executed against whatever `DATABASE_URL`
pointed at. A sweep that imported every backend module therefore created these
six tables in the live database:

    desires, emotion_breakdowns, pain_points,
    reddit_posts, sentiment_trends, trending_keywords

They belong to an older sentiment design that was never built. Nothing in the
running app reads or writes them — today's sentiment module stores everything in
`sentiment_analyses.analysis_data` (a JSONB column). They are empty and inert,
just clutter in the schema.

The script itself has been moved to `scripts/legacy/` so it can no longer run by
accident. This cleans up what it left behind.

USAGE
-----
    cd backend

    python scripts/drop_unused_sentiment_tables.py            # dry run
    python scripts/drop_unused_sentiment_tables.py --apply    # actually drop

It refuses to drop any table that has rows in it, so if one of these turns out
to be in use, nothing is lost.
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

TABLES = [
    "desires",
    "emotion_breakdowns",
    "pain_points",
    "reddit_posts",
    "sentiment_trends",
    "trending_keywords",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="actually drop (default is a dry run)")
    args = parser.parse_args()

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL is not set — check backend/.env")
        return 1

    engine = create_engine(db_url)

    with engine.connect() as conn:
        present = {r[0] for r in conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        ))}

        plan, skipped, missing = [], [], []
        for table in TABLES:
            if table not in present:
                missing.append(table)
                continue
            rows = conn.execute(text(f'SELECT count(*) FROM "{table}"')).scalar()
            if rows:
                skipped.append((table, rows))
            else:
                plan.append(table)

    if missing:
        print(f"already gone: {', '.join(missing)}")
    for table, rows in skipped:
        print(f"SKIP  {table} — has {rows} row(s), not touching it")
    for table in plan:
        print(f"DROP  {table} (empty)")

    if not plan:
        print("\nNothing to drop.")
        return 0

    if not args.apply:
        print("\nDry run — nothing changed. Re-run with --apply to drop them.")
        return 0

    with engine.begin() as conn:
        for table in plan:
            conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))
            print(f"dropped {table}")

    print(f"\nDone — removed {len(plan)} unused table(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
