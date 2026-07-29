"""Spec S — append-only undo log. Each mutation records its inverse as a new row;
`undo()` pops and applies the latest for the session. Best-effort: recording never raises."""
import json

from core.db import execute, query, rollback


DEFAULT_SESSION = "default"


def record(op: str, table: str, row_id=None, payload=None, session_id: str = DEFAULT_SESSION) -> None:
    """Store the inverse of the just-performed mutation. `op` is one of:
    'delete' (inverse of a create), 'restore' (inverse of a delete; payload = full row),
    'update' (inverse of an update; payload = prior values of changed columns).
    Single-level undo: only the latest mutation per session is undoable."""
    try:
        execute("DELETE FROM undo_log WHERE session_id = %s", (session_id,))
        execute(
            "INSERT INTO undo_log (session_id, op, target_table, row_id, payload) "
            "VALUES (%s, %s, %s, %s, %s)",
            (session_id, op, table, row_id, json.dumps(payload) if payload is not None else None),
        )
    except Exception:
        rollback()  # best-effort logging must not break the mutation it follows


def peek(session_id: str = DEFAULT_SESSION):
    row = query(
        "SELECT * FROM undo_log WHERE session_id = %s ORDER BY id DESC LIMIT 1",
        (session_id,),
        one=True,
    )
    return dict(row) if row else None


def undo(session_id: str = DEFAULT_SESSION) -> dict:
    """Apply the stored inverse for the latest mutation in this session and delete that row."""
    row = peek(session_id)
    if not row:
        return {"error": "nothing to undo"}
    op, table, row_id = row["op"], row["target_table"], row["row_id"]
    payload = json.loads(row["payload"]) if row["payload"] else None

    if op == "delete":                       # undo a create
        execute(f"DELETE FROM {table} WHERE id = %s", (row_id,))
    elif op == "restore":                    # undo a delete: re-insert (new id assigned)
        cols = [c for c in payload if c != "id"]
        execute(
            f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join(['%s'] * len(cols))})",
            [payload[c] for c in cols],
        )
    elif op == "update":                     # undo an update: restore prior column values
        cols = [c for c in payload if c != "id"]
        execute(
            f"UPDATE {table} SET {','.join(f'{c}=%s' for c in cols)} WHERE id = %s",
            [payload[c] for c in cols] + [row_id],
        )

    execute("DELETE FROM undo_log WHERE id = %s", (row["id"],))
    return {"undone": op, "table": table}