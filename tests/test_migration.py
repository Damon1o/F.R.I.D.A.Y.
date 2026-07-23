import sqlite3

from scripts.sqlite_to_pg import TABLES, copy_rows


class FakeCursor:
    def __init__(self, sink): self.sink = sink
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, params=()): self.sink.append((sql, tuple(params)))


class FakePg:
    def __init__(self): self.calls = []; self.commits = 0
    def cursor(self): return FakeCursor(self.calls)
    def commit(self): self.commits += 1


def test_copy_rows_inserts_every_table_with_pg_placeholders():
    src = sqlite3.connect(":memory:")
    src.row_factory = sqlite3.Row
    src.executescript(
        "CREATE TABLE settings(key TEXT, value TEXT, updated_at TEXT);"
        "CREATE TABLE events(id INTEGER PRIMARY KEY, title TEXT, start_at TEXT, end_at TEXT,"
        " all_day INT, location TEXT, notes TEXT, created_at TEXT);"
        "CREATE TABLE todos(id INTEGER PRIMARY KEY, title TEXT, due_at TEXT, done INT,"
        " notes TEXT, created_at TEXT, completed_at TEXT);"
        "CREATE TABLE messages(id INTEGER PRIMARY KEY, role TEXT, content TEXT, tool_calls TEXT,"
        " tool_call_id TEXT, name TEXT, created_at TEXT);"
        "INSERT INTO settings VALUES('nav_collapsed','true','2026-07-23 10:00:00');"
        "INSERT INTO todos(title,due_at,done,notes,created_at,completed_at)"
        " VALUES('Buy milk',NULL,0,NULL,'2026-07-23 10:00:00',NULL);"
    )
    pg = FakePg()
    copy_rows(src, pg)

    sqls = [c[0] for c in pg.calls]
    # one insert per source row, all using %s, never ?
    assert any("INSERT INTO settings" in s for s in sqls)
    assert any("INSERT INTO todos" in s for s in sqls)
    assert all("?" not in s for s in sqls)
    assert all("%s" in s for s in sqls)
    # the todo row's title is carried through
    todo_call = next(c for c in pg.calls if "INTO todos" in c[0])
    assert "Buy milk" in todo_call[1]
    assert pg.commits >= 1
