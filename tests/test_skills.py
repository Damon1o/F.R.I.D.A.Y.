"""Spec Y part one — skills: trigger selection in the system prompt, model, page, tools."""
import pytest

from pages.calendar.models import ValidationError
from pages.friday.agent import _system
from pages.friday.tools import dispatch
from pages.skills import models as skills


def _mk(name="Weekly planning", trigger="plan my week, week ahead", body="Call list_events.", **kw):
    s = skills.create_skill(name, trigger, body)
    return skills.update_skill(s["id"], kw) if kw else s


# ---- selection ----

def test_matching_trigger_loads_body_and_others_do_not(ctx):
    _mk()
    _mk(name="Inbox triage", trigger="triage my inbox", body="Call list_unread.")
    prompt = _system("plan my week please")["content"]
    assert "Call list_events." in prompt
    assert "Call list_unread." not in prompt


def test_disabled_skill_never_loads(ctx):
    _mk(enabled=False)
    assert "Call list_events." not in _system("plan my week")["content"]


def test_at_most_two_skills_load(ctx):
    for i in range(3):
        _mk(name=f"S{i}", trigger="plan my week", body=f"BODY{i}")
    prompt = _system("plan my week")["content"]
    assert sum(f"BODY{i}" in prompt for i in range(3)) == 2


def test_no_skills_leaves_prompt_unchanged(ctx):
    assert _system("plan my week")["content"] == _system("")["content"]


def test_db_error_while_loading_does_not_raise(ctx, monkeypatch):
    monkeypatch.setattr(skills, "list_skills", lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    assert "F.R.I.D.A.Y." in _system("plan my week")["content"]


def test_trigger_match_is_case_insensitive_both_ways(ctx):
    _mk(trigger="Plan My Week")
    assert "Call list_events." in _system("PLAN MY WEEK")["content"]


def test_match_increments_used_count(ctx):
    s = _mk()
    _system("plan my week")
    assert skills.get_skill(s["id"])["used_count"] == 1


# ---- model ----

def test_create_requires_all_three_fields(ctx):
    with pytest.raises(ValidationError):
        skills.create_skill("name", "", "body")


def test_create_same_name_updates_in_place(ctx):
    s = _mk()
    again = skills.create_skill("Weekly planning", "week ahead", "New body.")
    assert again["id"] == s["id"] and again["body"] == "New body."


def test_delete(ctx):
    s = _mk()
    assert skills.delete_skill(s["id"]) is True
    assert skills.delete_skill(s["id"]) is False


# ---- tools ----

def test_skill_tools(ctx):
    created = dispatch("create_skill", {"name": "Brief", "trigger": "brief me", "body": "Do it."})
    assert created["name"] == "Brief"
    assert [s["name"] for s in dispatch("list_skills", {})] == ["Brief"]


# ---- page ----

def test_skills_page_crud(client):
    assert client.get("/skills").status_code == 200
    client.post("/skills", data={"name": "Brief", "trigger": "brief me", "body": "Do it."})
    assert b"Brief" in client.get("/skills").data
    with client.application.app_context():
        sid = skills.list_skills()[0]["id"]
    client.post(f"/skills/{sid}/toggle")
    with client.application.app_context():
        assert skills.get_skill(sid)["enabled"] is False
    client.post(f"/skills/{sid}/delete")
    with client.application.app_context():
        assert skills.list_skills() == []


def test_skills_page_rejects_blank(client):
    client.post("/skills", data={"name": "", "trigger": "x", "body": "y"})
    with client.application.app_context():
        assert skills.list_skills() == []
