# F.R.I.D.A.Y. — Notes / Memory Tool Design (Spec I)

**Date:** 2026-07-24
**Status:** Draft (design).
**Depends on:** Spec A.
**Related:** Spec Q (unified search indexes notes too).

## 1. Context

FRIDAY should remember free-form facts the user tells it — "my parking spot is
B12", "Kate's birthday is March 3", "wifi password is X". Not a calendar event,
not a todo: a durable note the assistant can store and recall. Two tools:
`remember` and `recall`.

## 2. Goals / Non-goals

**Goals**
- `remember(text)` → store a note.
- `recall(query)` → return notes matching the query.
- `list_notes` / `delete_note(id)`.
- A simple `/notes` page to view/delete (read + delete only).

**Non-goals**
- Vector/embeddings search — Postgres full-text (`tsvector`) is plenty for a
  single user's notes. No new infra, no embedding provider (YAGNI).
- Rich text, attachments, folders.
- Editing notes in the UI beyond delete (voice can `remember` a corrected fact).

## 3. Design

**Tools** (add to `TOOLS` + `dispatch`):
- `remember` {`text`: string} → insert `notes` row.
- `recall` {`query`: string} → full-text match, return top N `{id, text, created_at}`.
- `list_notes`, `delete_note` {`note_id`}.

**Search:** Postgres `to_tsvector('english', text)` with a GIN index; `recall`
runs `plainto_tsquery`. Fallback to `ILIKE %query%` if FTS returns nothing.

**Module** `pages/notes/models.py` (CRUD + search) + `routes.py` (`/notes` page,
`GET/DELETE /api/notes`). Tools call the models.

## 4. Data

```sql
CREATE TABLE notes (
  id SERIAL PRIMARY KEY,
  text TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX notes_fts ON notes USING GIN (to_tsvector('english', text));
```

## 5. Testing

- Unit: `remember` inserts; `recall` finds by keyword; ranking returns best match
  first; ILIKE fallback path.
- Unit: `delete_note` removes; missing id → error.

## 6. Risks

- **FTS language/config** — English config assumed; acceptable for one user.
- **Unbounded growth** — trivial at personal scale; no pruning needed now.
