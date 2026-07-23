"""Thin sqlite3 layer. One connection per request via Flask's `g`."""
import sqlite3
from pathlib import Path

from flask import current_app, g

SCHEMA = Path(__file__).resolve().parent.parent / "schema.sql"


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DB_PATH"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    """Create tables if absent. Safe to call on every boot."""
    get_db().executescript(SCHEMA.read_text(encoding="utf-8"))
    get_db().commit()


def query(sql: str, params=(), *, one: bool = False):
    rows = get_db().execute(sql, params).fetchall()
    return (rows[0] if rows else None) if one else rows


def execute(sql: str, params=()) -> sqlite3.Cursor:
    """Run a write and commit. Returns the cursor (for lastrowid/rowcount)."""
    db = get_db()
    cur = db.execute(sql, params)
    db.commit()
    return cur


def init_app(app) -> None:
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
