# AI Assistant Core (Backend, Router, Calendar Page) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable Flask app with a persistent chat panel, a Claude-tier difficulty router, a per-request skill/context loader, and a fully working Calendar page backed by SQLite — per `docs/superpowers/specs/2026-07-20-ai-assistant-core-design.md`.

**Architecture:** Single Flask process. `core/` holds the model-provider abstraction, the difficulty router, and the context loader. `pages/calendar/` holds the Calendar blueprint (model, actions, routes); `pages/chat/` holds the shared `/api/chat` endpoint every page's chat panel calls. Server-rendered Jinja templates + vanilla JS, no build step.

**Tech Stack:** Python 3.11+, Flask, Flask-SQLAlchemy, SQLite, `anthropic` Python SDK, pytest, vanilla JS/HTML/CSS.

## Global Constraints

- Only Anthropic is wired for real calls in this plan. `providers/openai_provider.py` must exist with the same interface as `AnthropicProvider` but raise `NotImplementedError` on every method — do not implement OpenAI calls now.
- No consensus/second-opinion mechanism. When the assistant lacks required info (e.g. no recurrence given), it must ask the user directly instead of guessing or self-checking.
- No JS framework, no npm/bundler. Plain `<script>` files loaded by Jinja templates.
- No Alembic/migrations. Use `db.create_all()` at startup.
- API key(s) load from a `.env` file via `python-dotenv`; never hardcode a key in source.
- Token usage from every Anthropic response must be tracked and exposed to the frontend (see Task 7).

---

## File Structure

```
ai-assistant/
  app.py
  config.py
  requirements.txt
  .env.example
  core/
    __init__.py
    db.py
    router.py
    context_loader.py
    providers/
      __init__.py
      base.py
      anthropic_provider.py
      openai_provider.py
  pages/
    __init__.py
    calendar/
      __init__.py
      models.py
      actions.py
      routes.py
    chat/
      __init__.py
      routes.py
  templates/
    base.html
    calendar.html
  static/
    js/chat.js
    js/calendar.js
    css/style.css
  tests/
    conftest.py
    test_router.py
    test_calendar_actions.py
    test_chat_route.py
```

---

### Task 1: Project scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `config.py`
- Create: `core/__init__.py`
- Create: `core/db.py`
- Create: `pages/__init__.py`
- Create: `app.py`
- Test: `tests/conftest.py`

**Interfaces:**
- Produces: `core.db.db` (a `flask_sqlalchemy.SQLAlchemy` instance), `config.Config` class with `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `SQLALCHEMY_DATABASE_URI`, `TOKEN_BUDGET_WARNING` attributes, `app.create_app(config_overrides: dict | None = None) -> Flask`.

- [ ] **Step 1: Write `requirements.txt`**

```
flask>=3.0
flask-sqlalchemy>=3.1
python-dotenv>=1.0
anthropic>=0.39
pytest>=8.0
```

- [ ] **Step 2: Write `.env.example`**

```
ANTHROPIC_API_KEY=your-anthropic-key-here
OPENAI_API_KEY=your-openai-key-here
```

- [ ] **Step 3: Write `config.py`**

```python
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///assistant.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TOKEN_BUDGET_WARNING = int(os.environ.get("TOKEN_BUDGET_WARNING", "50000"))
```

- [ ] **Step 4: Write `core/__init__.py`** (empty file)

- [ ] **Step 5: Write `core/db.py`**

```python
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
```

- [ ] **Step 6: Write `pages/__init__.py`** (empty file)

- [ ] **Step 7: Write `app.py`**

```python
from flask import Flask

from config import Config
from core.db import db


def create_app(config_overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)

    db.init_app(app)

    from pages.calendar.routes import calendar_bp
    from pages.chat.routes import chat_bp

    app.register_blueprint(calendar_bp)
    app.register_blueprint(chat_bp)

    with app.app_context():
        db.create_all()

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(debug=True)
```

- [ ] **Step 8: Write the failing test `tests/conftest.py`**

```python
import pytest

from app import create_app
from core.db import db


@pytest.fixture
def app():
    application = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        }
    )
    with application.app_context():
        yield application
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_app_boots(client):
    response = client.get("/calendar")
    assert response.status_code == 200
```

This test will fail until Tasks 5-8 add the calendar blueprint, so for this
task run it expecting an import error — that confirms scaffolding wiring is
at least attempted. Do not treat this as a green test yet.

- [ ] **Step 9: Run to observe the expected failure**

Run: `pytest tests/conftest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pages.calendar.routes'`
(This confirms `app.py` correctly tries to import the pieces later tasks build.)

- [ ] **Step 10: Commit**

```bash
git add requirements.txt .env.example config.py core/__init__.py core/db.py pages/__init__.py app.py tests/conftest.py
git commit -m "Scaffold Flask app, config, and shared db instance"
```

---

### Task 2: Provider abstraction (Anthropic wired, OpenAI stubbed)

**Files:**
- Create: `core/providers/__init__.py`
- Create: `core/providers/base.py`
- Create: `core/providers/anthropic_provider.py`
- Create: `core/providers/openai_provider.py`
- Test: `tests/test_providers.py`

**Interfaces:**
- Produces: `core.providers.base.Provider` (abstract base with `complete(self, system: str, messages: list[dict], tools: list[dict] | None, model: str) -> ProviderResponse`), `ProviderResponse` dataclass with fields `text: str`, `tool_calls: list[dict]`, `input_tokens: int`, `output_tokens: int`, `stop_reason: str`.
- Produces: `core.providers.anthropic_provider.AnthropicProvider(api_key: str)` implementing `Provider`.
- Produces: `core.providers.openai_provider.OpenAIProvider(api_key: str)` implementing `Provider`, every method raises `NotImplementedError("OpenAI provider not implemented yet")`.

- [ ] **Step 1: Write `core/providers/__init__.py`** (empty file)

- [ ] **Step 2: Write `core/providers/base.py`**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ProviderResponse:
    text: str
    tool_calls: list[dict] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ""


class Provider(ABC):
    @abstractmethod
    def complete(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None,
        model: str,
    ) -> ProviderResponse:
        raise NotImplementedError
```

- [ ] **Step 3: Write the failing test `tests/test_providers.py`**

```python
from unittest.mock import MagicMock, patch

import pytest

from core.providers.anthropic_provider import AnthropicProvider
from core.providers.openai_provider import OpenAIProvider


def _fake_anthropic_message():
    text_block = MagicMock(type="text", text="Hello there")
    usage = MagicMock(input_tokens=12, output_tokens=8)
    message = MagicMock(content=[text_block], usage=usage, stop_reason="end_turn")
    return message


def test_anthropic_provider_returns_text_response():
    provider = AnthropicProvider(api_key="fake-key")
    with patch.object(
        provider.client.messages, "create", return_value=_fake_anthropic_message()
    ):
        result = provider.complete(
            system="You are helpful.",
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            model="claude-haiku-4-5",
        )

    assert result.text == "Hello there"
    assert result.input_tokens == 12
    assert result.output_tokens == 8
    assert result.tool_calls == []


def test_anthropic_provider_extracts_tool_calls():
    tool_block = MagicMock(
        type="tool_use", id="tool_1", name="add_event", input={"title": "Dentist"}
    )
    usage = MagicMock(input_tokens=20, output_tokens=15)
    message = MagicMock(content=[tool_block], usage=usage, stop_reason="tool_use")

    provider = AnthropicProvider(api_key="fake-key")
    with patch.object(provider.client.messages, "create", return_value=message):
        result = provider.complete(
            system="You are helpful.",
            messages=[{"role": "user", "content": "add a dentist appt"}],
            tools=[{"name": "add_event"}],
            model="claude-sonnet-4-5",
        )

    assert result.tool_calls == [
        {"id": "tool_1", "name": "add_event", "input": {"title": "Dentist"}}
    ]
    assert result.stop_reason == "tool_use"


def test_openai_provider_raises_not_implemented():
    provider = OpenAIProvider(api_key="fake-key")
    with pytest.raises(NotImplementedError):
        provider.complete(system="x", messages=[], tools=None, model="gpt-4o")
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_providers.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.providers.anthropic_provider'`

- [ ] **Step 5: Write `core/providers/anthropic_provider.py`**

```python
import anthropic

from core.providers.base import Provider, ProviderResponse


class AnthropicProvider(Provider):
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)

    def complete(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None,
        model: str,
    ) -> ProviderResponse:
        kwargs = {
            "model": model,
            "max_tokens": 1024,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        message = self.client.messages.create(**kwargs)

        text = ""
        tool_calls = []
        for block in message.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    {"id": block.id, "name": block.name, "input": block.input}
                )

        return ProviderResponse(
            text=text,
            tool_calls=tool_calls,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            stop_reason=message.stop_reason,
        )
```

- [ ] **Step 6: Write `core/providers/openai_provider.py`**

```python
from core.providers.base import Provider, ProviderResponse


class OpenAIProvider(Provider):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def complete(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict] | None,
        model: str,
    ) -> ProviderResponse:
        raise NotImplementedError("OpenAI provider not implemented yet")
```

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/test_providers.py -v`
Expected: PASS (4 tests)

- [ ] **Step 8: Commit**

```bash
git add core/providers tests/test_providers.py
git commit -m "Add Provider abstraction with Anthropic implementation and OpenAI stub"
```

---

### Task 3: Difficulty router

**Files:**
- Create: `core/router.py`
- Test: `tests/test_router.py`

**Interfaces:**
- Consumes: `core.providers.base.Provider`, `core.providers.base.ProviderResponse`
- Produces: `core.router.RouteDecision` dataclass with fields `tier: str` (one of `"haiku"`, `"sonnet"`, `"opus"`), `skills: list[str]`. Produces `core.router.classify(provider: Provider, user_message: str, active_page: str) -> RouteDecision`. Produces `core.router.TIER_MODELS: dict[str, str]` mapping tier name to Anthropic model id.

- [ ] **Step 1: Write the failing test `tests/test_router.py`**

```python
import json
from unittest.mock import MagicMock

from core.providers.base import ProviderResponse
from core.router import classify


def _provider_returning(tier: str, skills: list[str]):
    provider = MagicMock()
    provider.complete.return_value = ProviderResponse(
        text=json.dumps({"tier": tier, "skills": skills}),
        tool_calls=[],
        input_tokens=50,
        output_tokens=10,
        stop_reason="end_turn",
    )
    return provider


def test_classify_returns_haiku_for_simple_request():
    provider = _provider_returning("haiku", ["calendar"])
    decision = classify(provider, "add lunch with Sam tomorrow at noon", "calendar")
    assert decision.tier == "haiku"
    assert decision.skills == ["calendar"]


def test_classify_returns_opus_for_complex_request():
    provider = _provider_returning("opus", ["calendar"])
    decision = classify(
        provider,
        "reorganize my next three weeks of appointments around a new work trip",
        "calendar",
    )
    assert decision.tier == "opus"


def test_classify_falls_back_to_sonnet_on_bad_json():
    provider = MagicMock()
    provider.complete.return_value = ProviderResponse(
        text="not json", tool_calls=[], input_tokens=5, output_tokens=5
    )
    decision = classify(provider, "hello", "calendar")
    assert decision.tier == "sonnet"
    assert decision.skills == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.router'`

- [ ] **Step 3: Write `core/router.py`**

```python
import json
from dataclasses import dataclass

from core.providers.base import Provider

TIER_MODELS = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-5",
    "opus": "claude-opus-4-5",
}

_CLASSIFIER_SYSTEM_PROMPT = """You are a request router for a personal AI assistant.
Given the user's message and which page of the app they're on, respond with ONLY
a JSON object (no other text) of the form:
{"tier": "haiku" | "sonnet" | "opus", "skills": ["<page-name>", ...]}

Tier guidance:
- "haiku": simple, unambiguous single-step requests
- "sonnet": default tier for most real work, multi-step reasoning, drafting
- "opus": genuinely complex, high-stakes, or multi-constraint planning

"skills" should list which page(s) this request needs tools/context for
(e.g. "calendar"). If none apply, use an empty list.
"""


@dataclass
class RouteDecision:
    tier: str
    skills: list[str]


def classify(provider: Provider, user_message: str, active_page: str) -> RouteDecision:
    response = provider.complete(
        system=_CLASSIFIER_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Active page: {active_page}\nMessage: {user_message}",
            }
        ],
        tools=None,
        model=TIER_MODELS["haiku"],
    )

    try:
        parsed = json.loads(response.text)
        tier = parsed.get("tier", "sonnet")
        skills = parsed.get("skills", [])
        if tier not in TIER_MODELS:
            tier = "sonnet"
        return RouteDecision(tier=tier, skills=skills)
    except (json.JSONDecodeError, AttributeError):
        return RouteDecision(tier="sonnet", skills=[])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_router.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add core/router.py tests/test_router.py
git commit -m "Add difficulty router that classifies requests into model tiers"
```

---

### Task 4: Context loader (per-request skill/tool loading)

**Files:**
- Create: `core/context_loader.py`
- Test: `tests/test_context_loader.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (standalone registry), but its `skills` param is populated from `RouteDecision.skills` produced in Task 3.
- Produces: `core.context_loader.build_context(skills: list[str]) -> dict` returning `{"system_prompt": str, "tools": list[dict]}`. Produces `core.context_loader.SKILL_REGISTRY: dict[str, dict]` — each entry has `"system_prompt"` and `"tools"` keys. `pages.calendar.routes` (Task 8) registers the calendar skill into this registry at import time via `core.context_loader.register_skill(name: str, system_prompt: str, tools: list[dict])`.

- [ ] **Step 1: Write the failing test `tests/test_context_loader.py`**

```python
from core.context_loader import build_context, register_skill

BASE_SYSTEM_PROMPT = (
    "You are a helpful personal assistant running inside a desktop web app."
)


def test_build_context_with_no_skills_returns_base_prompt():
    context = build_context([])
    assert context["system_prompt"] == BASE_SYSTEM_PROMPT
    assert context["tools"] == []


def test_build_context_includes_registered_skill():
    register_skill(
        "example",
        system_prompt="You can manage example items.",
        tools=[{"name": "add_example", "description": "add one"}],
    )
    context = build_context(["example"])
    assert "You can manage example items." in context["system_prompt"]
    assert context["tools"] == [{"name": "add_example", "description": "add one"}]


def test_build_context_ignores_unknown_skill_names():
    context = build_context(["does-not-exist"])
    assert context["system_prompt"] == BASE_SYSTEM_PROMPT
    assert context["tools"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_context_loader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.context_loader'`

- [ ] **Step 3: Write `core/context_loader.py`**

```python
BASE_SYSTEM_PROMPT = (
    "You are a helpful personal assistant running inside a desktop web app."
)

SKILL_REGISTRY: dict[str, dict] = {}


def register_skill(name: str, system_prompt: str, tools: list[dict]) -> None:
    SKILL_REGISTRY[name] = {"system_prompt": system_prompt, "tools": tools}


def build_context(skills: list[str]) -> dict:
    system_prompt = BASE_SYSTEM_PROMPT
    tools: list[dict] = []

    for skill_name in skills:
        skill = SKILL_REGISTRY.get(skill_name)
        if skill is None:
            continue
        system_prompt += "\n\n" + skill["system_prompt"]
        tools.extend(skill["tools"])

    return {"system_prompt": system_prompt, "tools": tools}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_context_loader.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add core/context_loader.py tests/test_context_loader.py
git commit -m "Add per-request skill/tool context loader"
```

---

### Task 5: Calendar `Event` model

**Files:**
- Create: `pages/calendar/__init__.py`
- Create: `pages/calendar/models.py`
- Test: `tests/test_calendar_models.py`

**Interfaces:**
- Consumes: `core.db.db`
- Produces: `pages.calendar.models.Event` SQLAlchemy model with columns `id (int, pk)`, `title (str)`, `start_datetime (datetime)`, `end_datetime (datetime)`, `recurrence_rule (str, nullable, default "none")`, `notes (str, nullable)`, `created_at (datetime, default utcnow)`. Produces `Event.to_dict(self) -> dict`.

- [ ] **Step 1: Write `pages/calendar/__init__.py`** (empty file)

- [ ] **Step 2: Write the failing test `tests/test_calendar_models.py`**

```python
from datetime import datetime

from core.db import db
from pages.calendar.models import Event


def test_event_round_trips_through_db(app):
    event = Event(
        title="Dentist",
        start_datetime=datetime(2026, 8, 4, 15, 0),
        end_datetime=datetime(2026, 8, 4, 15, 30),
        recurrence_rule="none",
    )
    db.session.add(event)
    db.session.commit()

    fetched = Event.query.filter_by(title="Dentist").one()
    assert fetched.recurrence_rule == "none"
    assert fetched.to_dict()["title"] == "Dentist"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_calendar_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pages.calendar.models'`

- [ ] **Step 4: Write `pages/calendar/models.py`**

```python
from datetime import datetime

from core.db import db


class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    start_datetime = db.Column(db.DateTime, nullable=False)
    end_datetime = db.Column(db.DateTime, nullable=False)
    recurrence_rule = db.Column(db.String(50), nullable=False, default="none")
    notes = db.Column(db.String(1000), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "start_datetime": self.start_datetime.isoformat(),
            "end_datetime": self.end_datetime.isoformat(),
            "recurrence_rule": self.recurrence_rule,
            "notes": self.notes,
        }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_calendar_models.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pages/calendar/__init__.py pages/calendar/models.py tests/test_calendar_models.py
git commit -m "Add Event model for the calendar page"
```

---

### Task 6: Calendar actions (add/update/delete/list)

**Files:**
- Create: `pages/calendar/actions.py`
- Test: `tests/test_calendar_actions.py`

**Interfaces:**
- Consumes: `pages.calendar.models.Event`, `core.db.db`
- Produces: `pages.calendar.actions.add_event(title: str, start_datetime: str, end_datetime: str, recurrence_rule: str = "none", notes: str | None = None) -> dict`, `update_event(event_id: int, **fields) -> dict | None`, `delete_event(event_id: int) -> bool`, `list_events(start_range: str, end_range: str) -> list[dict]`. All datetimes passed/returned as ISO-8601 strings; `dict` returns are `Event.to_dict()` output.

- [ ] **Step 1: Write the failing test `tests/test_calendar_actions.py`**

```python
from pages.calendar.actions import (
    add_event,
    delete_event,
    list_events,
    update_event,
)


def test_add_event_creates_row(app):
    result = add_event(
        title="Dentist",
        start_datetime="2026-08-04T15:00:00",
        end_datetime="2026-08-04T15:30:00",
    )
    assert result["title"] == "Dentist"
    assert result["recurrence_rule"] == "none"


def test_list_events_filters_by_range(app):
    add_event(
        title="In range",
        start_datetime="2026-08-04T15:00:00",
        end_datetime="2026-08-04T15:30:00",
    )
    add_event(
        title="Out of range",
        start_datetime="2026-09-01T09:00:00",
        end_datetime="2026-09-01T09:30:00",
    )

    results = list_events(
        start_range="2026-08-01T00:00:00", end_range="2026-08-31T23:59:59"
    )

    titles = [event["title"] for event in results]
    assert titles == ["In range"]


def test_update_event_changes_fields(app):
    created = add_event(
        title="Dentist",
        start_datetime="2026-08-04T15:00:00",
        end_datetime="2026-08-04T15:30:00",
    )
    updated = update_event(created["id"], recurrence_rule="monthly")
    assert updated["recurrence_rule"] == "monthly"


def test_update_event_returns_none_for_missing_id(app):
    assert update_event(9999, title="x") is None


def test_delete_event_removes_row(app):
    created = add_event(
        title="Dentist",
        start_datetime="2026-08-04T15:00:00",
        end_datetime="2026-08-04T15:30:00",
    )
    assert delete_event(created["id"]) is True
    assert list_events(
        start_range="2026-08-01T00:00:00", end_range="2026-08-31T23:59:59"
    ) == []


def test_delete_event_returns_false_for_missing_id(app):
    assert delete_event(9999) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_calendar_actions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pages.calendar.actions'`

- [ ] **Step 3: Write `pages/calendar/actions.py`**

```python
from datetime import datetime

from core.db import db
from pages.calendar.models import Event


def add_event(
    title: str,
    start_datetime: str,
    end_datetime: str,
    recurrence_rule: str = "none",
    notes: str | None = None,
) -> dict:
    event = Event(
        title=title,
        start_datetime=datetime.fromisoformat(start_datetime),
        end_datetime=datetime.fromisoformat(end_datetime),
        recurrence_rule=recurrence_rule,
        notes=notes,
    )
    db.session.add(event)
    db.session.commit()
    return event.to_dict()


def update_event(event_id: int, **fields) -> dict | None:
    event = db.session.get(Event, event_id)
    if event is None:
        return None

    for key, value in fields.items():
        if key in ("start_datetime", "end_datetime") and value is not None:
            value = datetime.fromisoformat(value)
        setattr(event, key, value)

    db.session.commit()
    return event.to_dict()


def delete_event(event_id: int) -> bool:
    event = db.session.get(Event, event_id)
    if event is None:
        return False
    db.session.delete(event)
    db.session.commit()
    return True


def list_events(start_range: str, end_range: str) -> list[dict]:
    start = datetime.fromisoformat(start_range)
    end = datetime.fromisoformat(end_range)
    events = (
        Event.query.filter(Event.start_datetime >= start, Event.start_datetime <= end)
        .order_by(Event.start_datetime)
        .all()
    )
    return [event.to_dict() for event in events]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_calendar_actions.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add pages/calendar/actions.py tests/test_calendar_actions.py
git commit -m "Add calendar CRUD actions"
```

---

### Task 7: Chat route (`/api/chat`) with tool-call execution loop

**Files:**
- Create: `pages/chat/__init__.py`
- Create: `pages/chat/routes.py`
- Test: `tests/test_chat_route.py`

**Interfaces:**
- Consumes: `core.router.classify`, `core.router.TIER_MODELS`, `core.context_loader.build_context`, `core.providers.anthropic_provider.AnthropicProvider`, `core.providers.base.Provider`, `pages.calendar.actions` (via a tool dispatch table registered by Task 8).
- Produces: `pages.chat.routes.chat_bp` (Flask `Blueprint`), `POST /api/chat` accepting JSON `{"message": str, "active_page": str}` and returning JSON `{"reply": str, "input_tokens": int, "output_tokens": int, "total_tokens": int, "budget_warning": bool}`. Produces `pages.chat.routes.TOOL_DISPATCH: dict[str, callable]` — a module-level dict that skill modules populate (Task 8 adds calendar entries) mapping tool name to the Python function that executes it.

- [ ] **Step 1: Write `pages/chat/__init__.py`** (empty file)

- [ ] **Step 2: Write the failing test `tests/test_chat_route.py`**

```python
import json
from unittest.mock import patch

from core.providers.base import ProviderResponse


def test_chat_endpoint_returns_plain_text_reply(client):
    fake_classify_response = ProviderResponse(
        text=json.dumps({"tier": "haiku", "skills": []}),
        input_tokens=10,
        output_tokens=5,
    )
    fake_reply_response = ProviderResponse(
        text="Sure, done!", input_tokens=30, output_tokens=10, stop_reason="end_turn"
    )

    with patch(
        "pages.chat.routes.AnthropicProvider.complete",
        side_effect=[fake_classify_response, fake_reply_response],
    ):
        response = client.post(
            "/api/chat",
            json={"message": "hello", "active_page": "calendar"},
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data["reply"] == "Sure, done!"
    assert data["total_tokens"] == 55
    assert data["budget_warning"] is False


def test_chat_endpoint_executes_tool_call_then_replies(client):
    fake_classify_response = ProviderResponse(
        text=json.dumps({"tier": "sonnet", "skills": ["calendar"]}),
        input_tokens=10,
        output_tokens=5,
    )
    fake_tool_call_response = ProviderResponse(
        text="",
        tool_calls=[
            {
                "id": "tool_1",
                "name": "add_event",
                "input": {
                    "title": "Dentist",
                    "start_datetime": "2026-08-04T15:00:00",
                    "end_datetime": "2026-08-04T15:30:00",
                },
            }
        ],
        input_tokens=40,
        output_tokens=20,
        stop_reason="tool_use",
    )
    fake_final_response = ProviderResponse(
        text="Added your dentist appointment.",
        input_tokens=60,
        output_tokens=15,
        stop_reason="end_turn",
    )

    with patch(
        "pages.chat.routes.AnthropicProvider.complete",
        side_effect=[
            fake_classify_response,
            fake_tool_call_response,
            fake_final_response,
        ],
    ):
        response = client.post(
            "/api/chat",
            json={"message": "add a dentist appt next tuesday 3pm", "active_page": "calendar"},
        )

    data = response.get_json()
    assert data["reply"] == "Added your dentist appointment."
    assert data["total_tokens"] == 10 + 5 + 40 + 20 + 60 + 15


def test_chat_endpoint_flags_budget_warning_when_over_threshold(client, app):
    app.config["TOKEN_BUDGET_WARNING"] = 10

    fake_classify_response = ProviderResponse(
        text=json.dumps({"tier": "haiku", "skills": []}),
        input_tokens=10,
        output_tokens=5,
    )
    fake_reply_response = ProviderResponse(
        text="Hi!", input_tokens=10, output_tokens=5, stop_reason="end_turn"
    )

    with patch(
        "pages.chat.routes.AnthropicProvider.complete",
        side_effect=[fake_classify_response, fake_reply_response],
    ):
        response = client.post(
            "/api/chat", json={"message": "hi", "active_page": "calendar"}
        )

    assert response.get_json()["budget_warning"] is True
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_chat_route.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pages.chat.routes'`

- [ ] **Step 4: Write `pages/chat/routes.py`**

```python
from flask import Blueprint, current_app, jsonify, request

from core.context_loader import build_context
from core.providers.anthropic_provider import AnthropicProvider
from core.router import TIER_MODELS, classify

chat_bp = Blueprint("chat", __name__)

TOOL_DISPATCH: dict[str, callable] = {}

MAX_TOOL_ITERATIONS = 5


@chat_bp.route("/api/chat", methods=["POST"])
def chat():
    payload = request.get_json()
    user_message = payload["message"]
    active_page = payload.get("active_page", "")

    provider = AnthropicProvider(api_key=current_app.config["ANTHROPIC_API_KEY"])

    decision = classify(provider, user_message, active_page)
    context = build_context(decision.skills)

    total_input_tokens = 0
    total_output_tokens = 0

    messages = [{"role": "user", "content": user_message}]
    model = TIER_MODELS[decision.tier]

    reply_text = ""
    for _ in range(MAX_TOOL_ITERATIONS):
        response = provider.complete(
            system=context["system_prompt"],
            messages=messages,
            tools=context["tools"] or None,
            model=model,
        )
        total_input_tokens += response.input_tokens
        total_output_tokens += response.output_tokens

        if not response.tool_calls:
            reply_text = response.text
            break

        messages.append({"role": "assistant", "content": response.text or ""})
        tool_results = []
        for call in response.tool_calls:
            handler = TOOL_DISPATCH.get(call["name"])
            result = handler(**call["input"]) if handler else {"error": "unknown tool"}
            tool_results.append(
                {"tool_use_id": call["id"], "content": str(result)}
            )
        messages.append({"role": "user", "content": str(tool_results)})
    else:
        reply_text = "Sorry, I couldn't finish that request."

    total_tokens = total_input_tokens + total_output_tokens
    budget_warning = total_tokens > current_app.config["TOKEN_BUDGET_WARNING"]

    return jsonify(
        {
            "reply": reply_text,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
            "total_tokens": total_tokens,
            "budget_warning": budget_warning,
        }
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_chat_route.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add pages/chat tests/test_chat_route.py
git commit -m "Add /api/chat endpoint with router, context loading, and tool-call loop"
```

---

### Task 8: Calendar blueprint (routes + skill registration) and app wiring

**Files:**
- Create: `pages/calendar/routes.py`
- Modify: `app.py` (already imports `pages.calendar.routes` and `pages.chat.routes` from Task 1 — no changes needed, this task makes those imports succeed)
- Test: `tests/test_calendar_routes.py`

**Interfaces:**
- Consumes: `pages.calendar.actions.add_event/update_event/delete_event/list_events`, `core.context_loader.register_skill`, `pages.chat.routes.TOOL_DISPATCH`.
- Produces: `pages.calendar.routes.calendar_bp` (Flask `Blueprint`) with `GET /calendar` (renders `calendar.html`) and `GET /calendar/api/events?start=...&end=...` (returns JSON list from `list_events`). Registers the `"calendar"` skill and its four tools into `context_loader.SKILL_REGISTRY` and `pages.chat.routes.TOOL_DISPATCH` at import time.

- [ ] **Step 1: Write the failing test `tests/test_calendar_routes.py`**

```python
def test_calendar_page_renders(client):
    response = client.get("/calendar")
    assert response.status_code == 200
    assert b"calendar" in response.data.lower()


def test_calendar_events_api_returns_json_list(client):
    response = client.get(
        "/calendar/api/events?start=2026-08-01T00:00:00&end=2026-08-31T23:59:59"
    )
    assert response.status_code == 200
    assert response.get_json() == []


def test_calendar_skill_is_registered_with_tools():
    from core.context_loader import SKILL_REGISTRY

    assert "calendar" in SKILL_REGISTRY
    tool_names = {tool["name"] for tool in SKILL_REGISTRY["calendar"]["tools"]}
    assert tool_names == {"add_event", "update_event", "delete_event", "list_events"}


def test_calendar_tools_are_registered_in_dispatch():
    from pages.chat.routes import TOOL_DISPATCH

    assert set(["add_event", "update_event", "delete_event", "list_events"]).issubset(
        TOOL_DISPATCH.keys()
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_calendar_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pages.calendar.routes'` (and Task 1's `conftest.py` test now also fails the same way, confirming the gap this task closes)

- [ ] **Step 3: Write `pages/calendar/routes.py`**

```python
from flask import Blueprint, render_template, request, jsonify

from core.context_loader import register_skill
from pages.calendar.actions import (
    add_event,
    delete_event,
    list_events,
    update_event,
)
from pages.chat.routes import TOOL_DISPATCH

calendar_bp = Blueprint("calendar", __name__)


@calendar_bp.route("/calendar")
def calendar_page():
    return render_template("calendar.html")


@calendar_bp.route("/calendar/api/events")
def calendar_events_api():
    start = request.args.get("start")
    end = request.args.get("end")
    return jsonify(list_events(start_range=start, end_range=end))


CALENDAR_TOOLS = [
    {
        "name": "add_event",
        "description": "Add a new calendar event. Ask the user first if recurrence "
        "or duration is unclear rather than guessing.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "start_datetime": {"type": "string", "description": "ISO-8601"},
                "end_datetime": {"type": "string", "description": "ISO-8601"},
                "recurrence_rule": {
                    "type": "string",
                    "enum": ["none", "daily", "weekly", "monthly"],
                },
                "notes": {"type": "string"},
            },
            "required": ["title", "start_datetime", "end_datetime"],
        },
    },
    {
        "name": "update_event",
        "description": "Update fields on an existing event by id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "integer"},
                "title": {"type": "string"},
                "start_datetime": {"type": "string"},
                "end_datetime": {"type": "string"},
                "recurrence_rule": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "delete_event",
        "description": "Delete an event by id. Confirm with the user before "
        "deleting if the request is ambiguous about which event is meant.",
        "input_schema": {
            "type": "object",
            "properties": {"event_id": {"type": "integer"}},
            "required": ["event_id"],
        },
    },
    {
        "name": "list_events",
        "description": "List events between two ISO-8601 datetimes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "start_range": {"type": "string"},
                "end_range": {"type": "string"},
            },
            "required": ["start_range", "end_range"],
        },
    },
]

register_skill(
    "calendar",
    system_prompt=(
        "The user is on the Calendar page. You can add, update, delete, and list "
        "events with the provided tools. If recurrence or any other required "
        "detail is missing or ambiguous, ask the user directly instead of "
        "guessing."
    ),
    tools=CALENDAR_TOOLS,
)

TOOL_DISPATCH.update(
    {
        "add_event": add_event,
        "update_event": update_event,
        "delete_event": delete_event,
        "list_events": list_events,
    }
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_calendar_routes.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full suite to confirm Task 1's scaffolding test now passes too**

Run: `pytest -v`
Expected: PASS (all tests across all files)

- [ ] **Step 6: Commit**

```bash
git add pages/calendar/routes.py tests/test_calendar_routes.py
git commit -m "Add calendar routes, register calendar skill and tool dispatch"
```

---

### Task 9: Templates and static assets (base layout, chat panel, calendar view)

**Files:**
- Create: `templates/base.html`
- Create: `templates/calendar.html`
- Create: `static/css/style.css`
- Create: `static/js/chat.js`
- Create: `static/js/calendar.js`

**Interfaces:**
- Consumes: `GET /calendar/api/events`, `POST /api/chat` (both from Tasks 7-8).
- Produces: rendered pages a human can use in a browser. No new Python interfaces — this task is UI only and is verified manually (per the spec's testing approach), not with pytest.

- [ ] **Step 1: Write `templates/base.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{% block title %}AI Assistant{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
</head>
<body data-active-page="{{ active_page }}">
  <div class="layout">
    <nav class="sidebar">
      <a href="{{ url_for('calendar.calendar_page') }}">Calendar</a>
    </nav>
    <main class="page-content">
      {% block content %}{% endblock %}
    </main>
    <aside class="chat-panel">
      <div id="chat-messages" class="chat-messages"></div>
      <div id="token-usage" class="token-usage"></div>
      <form id="chat-form">
        <textarea id="chat-input" placeholder="Ask your assistant..."></textarea>
        <button type="submit">Send</button>
      </form>
    </aside>
  </div>
  <script src="{{ url_for('static', filename='js/chat.js') }}"></script>
  {% block scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 2: Write `templates/calendar.html`**

```html
{% extends "base.html" %}
{% set active_page = "calendar" %}
{% block title %}Calendar - AI Assistant{% endblock %}
{% block content %}
<h1>Calendar</h1>
<div id="calendar-grid" class="calendar-grid"></div>
{% endblock %}
{% block scripts %}
<script src="{{ url_for('static', filename='js/calendar.js') }}"></script>
{% endblock %}
```

- [ ] **Step 3: Write `static/css/style.css`**

```css
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, sans-serif; }
.layout { display: grid; grid-template-columns: 180px 1fr 320px; height: 100vh; }
.sidebar { background: #1f2430; color: #fff; padding: 1rem; }
.sidebar a { color: #fff; display: block; padding: 0.5rem 0; text-decoration: none; }
.page-content { padding: 1.5rem; overflow-y: auto; }
.chat-panel { display: flex; flex-direction: column; border-left: 1px solid #ddd; padding: 1rem; }
.chat-messages { flex: 1; overflow-y: auto; }
.token-usage { font-size: 0.8rem; color: #888; padding: 0.25rem 0; }
#chat-form { display: flex; gap: 0.5rem; }
#chat-input { flex: 1; resize: none; height: 3rem; }
.calendar-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; }
.calendar-day { border: 1px solid #eee; min-height: 80px; padding: 4px; font-size: 0.8rem; }
```

- [ ] **Step 4: Write `static/js/chat.js`**

```javascript
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const messages = document.getElementById("chat-messages");
  const tokenUsage = document.getElementById("token-usage");
  const activePage = document.body.dataset.activePage || "";

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message) return;

    appendMessage("you", message);
    input.value = "";

    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, active_page: activePage }),
    });
    const data = await response.json();

    appendMessage("assistant", data.reply);
    tokenUsage.textContent = `Tokens used this reply: ${data.total_tokens}`;
    if (data.budget_warning) {
      appendMessage(
        "system",
        "This conversation is getting long — consider starting a fresh one."
      );
    }

    if (activePage === "calendar" && typeof window.refreshCalendar === "function") {
      window.refreshCalendar();
    }
  });

  function appendMessage(sender, text) {
    const el = document.createElement("div");
    el.className = `chat-message chat-message--${sender}`;
    el.textContent = text;
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
  }
});
```

- [ ] **Step 5: Write `static/js/calendar.js`**

```javascript
async function refreshCalendar() {
  const grid = document.getElementById("calendar-grid");
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), 1);
  const end = new Date(now.getFullYear(), now.getMonth() + 1, 0, 23, 59, 59);

  const response = await fetch(
    `/calendar/api/events?start=${start.toISOString()}&end=${end.toISOString()}`
  );
  const events = await response.json();

  grid.innerHTML = "";
  for (const event of events) {
    const el = document.createElement("div");
    el.className = "calendar-day";
    el.textContent = `${event.title} — ${new Date(event.start_datetime).toLocaleString()}`;
    grid.appendChild(el);
  }
}

window.refreshCalendar = refreshCalendar;
document.addEventListener("DOMContentLoaded", refreshCalendar);
```

- [ ] **Step 6: Commit**

```bash
git add templates static
git commit -m "Add base layout, chat panel, and calendar view templates/JS/CSS"
```

---

### Task 10: End-to-end manual verification

**Files:** none (verification only)

- [ ] **Step 1: Create a real `.env` from `.env.example` and add a real Anthropic key**

```bash
cp .env.example .env
```
Then edit `.env` and set `ANTHROPIC_API_KEY` to a real key (never commit this file — confirm `.env` is in `.gitignore`).

- [ ] **Step 2: Add a `.gitignore` if one doesn't exist**

```bash
printf ".env\n__pycache__/\n*.pyc\nassistant.db\n" > .gitignore
git add .gitignore
git commit -m "Add .gitignore for env, bytecode, and local db"
```

- [ ] **Step 3: Install dependencies**

Run: `pip install -r requirements.txt`
Expected: all packages install without error

- [ ] **Step 4: Run the full automated test suite**

Run: `pytest -v`
Expected: all tests pass

- [ ] **Step 5: Run the app**

Run: `python app.py`
Expected: Flask dev server starts on `http://127.0.0.1:5000`

- [ ] **Step 6: Manually verify in a browser**

Open `http://127.0.0.1:5000/calendar`. In the chat panel, type: "add a dentist appointment next Tuesday at 3pm". Confirm:
- The assistant either asks a clarifying question about recurrence, or adds the event and confirms
- After confirmation, the event appears in the calendar grid without a page reload
- The token-usage line under the chat updates after each reply

Then type a destructive/ambiguous request, e.g. "delete my appointment" (with more than one event present). Confirm the assistant asks which one you mean rather than guessing.

- [ ] **Step 7: Report results to the user**

Summarize what worked and any issues found. Do not mark this plan complete until this manual pass has actually been run against a real API key — the automated tests mock the provider and cannot catch real prompt/tool-schema mismatches with the live Anthropic API.
