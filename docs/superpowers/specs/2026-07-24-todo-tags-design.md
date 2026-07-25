# F.R.I.D.A.Y. — Todo Tags / Projects Design (Spec R)

**Date:** 2026-07-24
**Status:** Draft (design).
**Depends on:** Spec A (todos model + `/api/todos`).

## 1. Context

Group and filter todos — "work", "home", "groceries". Lightweight labelling, not a
project-management system. Add a simple tag on todos and filtering by it.

## 2. Goals / Non-goals

**Goals**
- Todos gain tags; filter list by tag (UI + API + agent tool param).
- Create/assign tags by name inline (typing/saying a tag creates it).
- Tag chips in the todo UI; a tag filter.

**Non-goals**
- Tags on events (todos first; extend later if it earns its keep).
- Tag colors, hierarchy, per-tag views/boards, shared/assigned tags.
- A separate many-to-many `tags` table if a single label suffices — **decide in
  plan** (see §3); prefer the simplest that meets "filter by one tag".

## 3. Design

**Data — pick the lazy option that fits usage:**
- **Option A (start here):** a nullable `todos.tag TEXT` — one tag per todo.
  Filtering is `WHERE tag = %s`. Zero join, covers the stated need.
- **Option B (only if multi-tag is actually needed):** `tags` + `todo_tags`
  join. Don't build this until one-tag-per-todo proves insufficient (YAGNI).

Spec commits to **Option A** unless the user says a todo needs multiple tags.

**API/tools:**
- `list_todos` gains `tag` filter (route `?tag=`, tool param, model `WHERE`).
- `create_todo`/`update_todo` accept `tag`.
- `GET /api/tags` → distinct tags in use (for the filter UI / autocomplete).

**UI:** tag chip on each todo; a tag dropdown/filter on the todo page.

## 4. Testing

- Unit: create/update with a tag; `list_todos(tag=...)` filters correctly;
  no-tag lists everything.
- Unit: `/api/tags` returns distinct tags.

## 5. Risks

- **Option creep** — resist Option B until multi-tag is a real need.
- **Tag typos** create near-duplicates — `/api/tags` autocomplete mitigates.
