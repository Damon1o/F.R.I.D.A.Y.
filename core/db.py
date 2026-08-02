"""Thin psycopg 3 layer. One connection per request via Flask's `g`."""
import psycopg
from psycopg.rows import dict_row
from pathlib import Path

from flask import current_app, g

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"


def get_db() -> psycopg.Connection:
    if "db" not in g:
        # connect_timeout: without it a machine that is offline (or behind a firewall that
        # drops rather than refuses) blocks here forever — the desktop window would just sit
        # blank instead of reaching the offline page.
        g.db = psycopg.connect(current_app.config["DATABASE_URL"], row_factory=dict_row,
                               prepare_threshold=None, connect_timeout=5)
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    """Create tables if absent. Safe to call on every boot."""
    db = get_db()
    db.execute(SCHEMA.read_text(encoding="utf-8"))
    db.commit()


def query(sql: str, params=(), *, one: bool = False):
    rows = get_db().execute(sql, params).fetchall()
    return (rows[0] if rows else None) if one else rows


def execute(sql: str, params=()):
    """Run a write and commit. Returns the committed cursor (for rowcount / RETURNING)."""
    db = get_db()
    cur = db.execute(sql, params)
    db.commit()
    return cur


def rollback() -> None:
    """Clear a failed transaction. Postgres refuses every later statement on the
    connection until this runs, so swallowing an error without it poisons the
    rest of the request."""
    db = g.get("db")
    if db is not None:
        db.rollback()


def init_app(app) -> None:
    # No eager connect: on serverless a DB hiccup here would crash the whole
    # function import and 500 every route. Schema is owned by the migration
    # script; connections stay lazy (per-request via get_db).
    app.teardown_appcontext(close_db)
