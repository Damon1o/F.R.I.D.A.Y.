"""One-shot copy of a local friday.db (SQLite) into Postgres. Run once, locally.

Usage:
    DATABASE_URL=postgresql://... python -m scripts.sqlite_to_pg [path/to/friday.db]

IDs are reassigned by Postgres identity columns (single user, no external id refs).
Timestamps and all other values are preserved verbatim.
"""
import os
import sqlite3
import sys

import psycopg

# table -> columns copied (id omitted so Postgres identity assigns fresh ids)
TABLES = {
    "settings": ("key", "value", "updated_at"),
    "events": ("title", "start_at", "end_at", "all_day", "location", "notes", "created_at"),
    "todos": ("title", "due_at", "done", "notes", "created_at", "completed_at"),
    "messages": ("role", "content", "tool_calls", "tool_call_id", "name", "created_at"),
}


def copy_rows(sqlite_conn, pg_conn) -> None:
    for table, cols in TABLES.items():
        rows = sqlite_conn.execute(f"SELECT {','.join(cols)} FROM {table}").fetchall()
        collist = ",".join(cols)
        placeholders = ",".join(["%s"] * len(cols))
        with pg_conn.cursor() as cur:
            for row in rows:
                cur.execute(
                    f"INSERT INTO {table} ({collist}) VALUES ({placeholders})",
                    tuple(row[c] for c in cols),
                )
        pg_conn.commit()
        print(f"  {table}: {len(rows)} rows")


def main() -> None:
    db_path = sys.argv[1] if len(sys.argv) > 1 else "friday.db"
    url = os.environ["DATABASE_URL"]
    src = sqlite3.connect(db_path)
    src.row_factory = sqlite3.Row
    with psycopg.connect(url) as pg:
        print(f"Copying {db_path} -> Postgres")
        copy_rows(src, pg)
    src.close()
    print("Done.")


if __name__ == "__main__":
    main()
