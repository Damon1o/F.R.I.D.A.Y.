"""Spec S — single-level undo. Each mutation records its inverse (overwriting the
prior one); `undo()` replays that inverse. Best-effort: recording never raises into
the caller. Table names come from internal constants only (safe to interpolate)."""
import json

from core.db import execute, query


def record(op: str, table: str, row_id=None, payload=None) -> None:
    """Store the inverse of the just-performed mutation. `op` is one of:
    'delete' (inverse of a create), 'restore' (inverse of a delete; payload = full row),
    'update' (inverse of an update; payload = prior values of changed columns)."""
    try:
        execute(
            "INSERT INTO undo_log (id, op, target_table, row_id, payload) VALUES (1, %s, %s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET op=excluded.op, target_table=excluded.target_table, "
            "row_id=excluded.row_id, payload=excluded.payload, "
            "created_at=to_char(now() at time zone 'utc', 'YYYY-MM-DD HH24:MI:SS')",
            (op, table, row_id, json.dumps(payload) if payload is not None else None),
        )
    except Exception:
        pass


def peek():
    row = query("SELECT * FROM undo_log WHERE id = 1", one=True)
    return dict(row) if row else None


def undo() -> dict:
    """Apply the stored inverse and clear it. Returns a small status dict."""
    row = peek()
    if not row:
        return {"error": "nothing to undo"}
    op, table, row_id = row["op"], row["target_table"], row["row_id"]
    payload = json.loads(row["payload"]) if row["payload"] else None

    if op == "delete":                       # undo a create
        execute(f"DELETE FROM {table} WHERE id = %s", (row_id,))
    elif op == "restore":                    # undo a delete: re-insert (new id assigned)
        cols = [c for c in payload if c != "id"]
        execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join(['%s'] * len(cols))})",
                [payload[c] for c in cols])
    elif op == "update":                     # undo an update: restore prior column values
        cols = [c for c in payload if c != "id"]
        execute(f"UPDATE {table} SET {','.join(f'{c}=%s' for c in cols)} WHERE id = %s",
                [payload[c] for c in cols] + [row_id])

    execute("DELETE FROM undo_log WHERE id = 1")
    return {"undone": op, "table": table}
