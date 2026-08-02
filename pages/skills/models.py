"""Spec Y — skills: named instruction blocks the agent loads when a trigger matches."""
from core.db import execute, query
from pages.calendar.models import ValidationError


def list_skills(enabled: bool | None = None) -> list[dict]:
    sql = "SELECT * FROM skills"
    params: tuple = ()
    if enabled is not None:
        sql += " WHERE enabled = %s"
        params = (enabled,)
    return [dict(r) for r in query(sql + " ORDER BY name", params)]


def get_skill(skill_id: int):
    row = query("SELECT * FROM skills WHERE id = %s", (skill_id,), one=True)
    return dict(row) if row else None


def create_skill(name: str, trigger: str, body: str) -> dict:
    name, trigger, body = (name or "").strip(), (trigger or "").strip(), (body or "").strip()
    if not (name and trigger and body):
        raise ValidationError("name, trigger and body are required")
    row = execute(
        "INSERT INTO skills (name, trigger, body) VALUES (%s, %s, %s) "
        "ON CONFLICT (name) DO UPDATE SET trigger = EXCLUDED.trigger, body = EXCLUDED.body "
        "RETURNING id",
        (name, trigger, body),
    ).fetchone()
    return get_skill(row["id"])


def update_skill(skill_id: int, fields: dict):
    allowed = {k: v for k, v in fields.items() if k in ("name", "trigger", "body", "enabled")}
    if not allowed:
        return get_skill(skill_id)
    sets = ", ".join(f"{k} = %s" for k in allowed)
    execute(f"UPDATE skills SET {sets} WHERE id = %s", (*allowed.values(), skill_id))
    return get_skill(skill_id)


def delete_skill(skill_id: int) -> bool:
    return execute("DELETE FROM skills WHERE id = %s", (skill_id,)).rowcount > 0


def mark_used(ids) -> None:
    if ids:
        execute("UPDATE skills SET used_count = used_count + 1 WHERE id = ANY(%s)", (list(ids),))
