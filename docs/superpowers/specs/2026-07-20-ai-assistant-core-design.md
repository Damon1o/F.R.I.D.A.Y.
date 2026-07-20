# AI Assistant — Core Design (Spec 1: Backend, Router, Calendar Page)

## Overview & Scope

This is the first of several planned specs for a personal, locally-run AI assistant
web app. Spec 1 delivers a working, runnable Flask app with:

- A persistent chat panel visible on every page — the primary way to talk to the assistant
- A difficulty-router that classifies each request and dispatches it to a Claude
  model tier (Haiku / Sonnet / Opus) based on how hard the request is
- A context/skill loader that only includes the tool definitions and prompt
  content relevant to the current request, to keep token usage down
- One fully working page: **Calendar** — add/view/edit/delete events via chat,
  with the assistant asking clarifying questions ("does this repeat?") when
  details are missing, instead of guessing
- SQLite storage
- Token-usage visibility in the chat panel

Out of scope for Spec 1 (planned as follow-up specs):
- Spec 2: Notes and Task/To-do pages (reuse the blueprint/action pattern from Calendar)
- Spec 3: Voice-input polish for Wispr Flow (no API integration needed — Wispr Flow
  is an OS-level dictation tool that types into any focused text field; this just
  means keeping chat/page inputs as plain `<textarea>`/`<input>` elements)
- Spec 4: Windows auto-boot on startup (Task Scheduler entry or Startup-folder
  shortcut that runs `python app.py` and opens the browser)

## Decisions Made During Brainstorming

- **Model provider**: Anthropic (Claude) fully wired for Spec 1. An OpenAI adapter
  is stubbed behind the same interface for a later spec — not built now.
- **"ECC" (github.com/affaan-m/ecc)**: investigated and found to be a third-party
  Claude Code plugin (skills/instincts/memory optimization for the coding agent
  itself), not a multi-model consensus/council library, and not something that runs
  inside the app. Decision: skip installing it — its stated purpose already
  overlaps with skills already available (e.g. `ponytail`).
- **Multi-model "consensus check" for risky actions**: originally considered as a
  second-opinion API call before destructive actions (e.g. deleting an event).
  Decision: dropped for v1 as unnecessary complexity. Instead, the assistant asks
  the user directly whenever it's unsure or a requested action is ambiguous/destructive.
- **Chat placement**: one persistent chat panel present on every page (not a
  separate chat per page). The assistant knows which page is currently active and
  can act on it, but a single continuous conversation spans all pages.
- **Frontend approach**: server-rendered Flask + Jinja templates with vanilla JS
  for interactivity. No JS framework, no npm build step — matches the simplicity
  goal for a personal desktop app.
- **Calendar storage**: local SQLite database (not synced to Google Calendar).
  Fully private, no external account/OAuth setup required.
- **Token budget**: soft warning only (default threshold: 50k tokens per session),
  not a hard cutoff — the assistant flags long conversations so the user can start fresh.

## Architecture

```
ai-assistant/
  app.py                  # Flask entry point, registers page blueprints
  config.py                # loads API keys from .env
  /core
    router.py              # difficulty classifier -> picks model tier
    providers/
      anthropic_provider.py   # wired: haiku/sonnet/opus tiers
      openai_provider.py      # stub: raises NotImplementedError, same interface
    context_loader.py      # picks which "skill" context/tools to include per request
  /pages
    calendar/
      routes.py            # Flask blueprint: /calendar
      models.py             # SQLAlchemy Event model
      actions.py            # add_event/update_event/delete_event/list_events
    chat/
      routes.py             # /api/chat endpoint, shared by every page
  /templates
    base.html               # shared layout: sidebar nav + persistent chat panel
    calendar.html
  /static
    js/chat.js               # posts messages to /api/chat, renders replies
    js/calendar.js
    css/style.css
  assistant.db              # SQLite
  .env                      # ANTHROPIC_API_KEY=...
```

### Request flow

1. User types in the chat panel (on any page).
2. JS posts the message + current page context to `/api/chat`.
3. `router.py` classifies difficulty/intent via a small Haiku call, returning a
   model tier and which page-skill(s) to load.
4. `context_loader.py` assembles only the relevant tool definitions and
   system-prompt slice for the request (e.g. calendar tools only load when the
   user is on/talking about Calendar).
5. The chosen model tier responds, optionally calling an action function
   (e.g. `add_event`).
6. If the action is ambiguous or missing required info (e.g. no recurrence
   specified), the assistant asks the user directly rather than guessing.
7. The result streams back to the chat panel; the active page's data updates.

### Model tiers

- **Tier 1 — Haiku**: simple/unambiguous requests (add a specific event, look up
  a note, small talk)
- **Tier 2 — Sonnet**: default tier — most real work, multi-step reasoning, drafting
- **Tier 3 — Opus**: genuinely hard/high-stakes requests (complex planning,
  anything the user flags as important)

The router's own classification call uses Haiku and is kept intentionally small
so it doesn't undercut the token savings it's meant to produce.

### Token budget visibility

The chat panel shows a running token counter for the session. When it crosses a
threshold (default: 50,000 tokens, configurable), the assistant flags it in-chat
("this conversation is getting long — consider starting fresh") rather than
silently continuing to grow. This is a soft, in-UI signal, not an enforced cutoff.

## Calendar Page

- **Data model**: `Event(id, title, start_datetime, end_datetime, recurrence_rule,
  notes, created_at)`. Recurrence is a simple rule (none/daily/weekly/monthly/custom),
  not a full iCal RRULE engine.
- **Views**: month grid (default) plus a day/agenda list. Server-rendered + JS for
  interaction. Drag-to-reschedule is not in scope for v1; click to add/edit.
- **Assistant behavior**: given "add a dentist appointment next Tuesday at 3pm,"
  the assistant fills in what it can infer and asks only about genuinely missing
  or ambiguous details (e.g. "does this repeat?"), without asking about things it
  can reasonably default (e.g. a 30-minute duration) unless corrected.
- **Actions exposed to the model**: `add_event`, `update_event`, `delete_event`,
  `list_events(range)`. These are the "calendar skill" tools that `context_loader.py`
  only loads when relevant to the current request.

## Storage & Testing

- **Storage**: SQLite via SQLAlchemy, single `assistant.db` file. No migrations
  framework for now (add Alembic later only if the schema starts churning).
- **Testing**: pytest covering the router's tier-selection logic and the calendar
  CRUD action functions. UI is verified manually in-browser (personal app, not
  shipping to other users).

## Roadmap After Spec 1

- **Spec 2**: Notes and Task/To-do pages, built by reusing the Calendar page's
  blueprint + actions pattern.
- **Spec 3**: Voice-input polish for Wispr Flow. No API work required — Wispr
  Flow dictates into whatever text field has focus, so this just means keeping
  chat/page inputs as plain, standard form elements.
- **Spec 4**: Windows auto-boot on startup — a Task Scheduler entry or
  Startup-folder shortcut that launches `python app.py` and opens the browser to
  the app automatically.
