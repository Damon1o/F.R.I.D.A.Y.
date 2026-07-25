# F.R.I.D.A.Y. — Unified Search Design (Spec Q)

**Date:** 2026-07-24
**Status:** Draft (design).
**Depends on:** Spec A. **Related:** Spec I (notes), Spec L (recurring events).

## 1. Context

One search box that spans events, todos, and notes — "find everything about the
dentist". Both a UI feature (a search page / command box) and a `search_all` agent
tool.

## 2. Goals / Non-goals

**Goals**
- `GET /api/search?q=` → `{events:[...], todos:[...], notes:[...]}`.
- A search UI (top-bar box or `/search` page) rendering grouped results.
- `search_all(query)` agent tool returning the same grouped result.

**Non-goals**
- A dedicated search engine (Elastic/Meili). Postgres `ILIKE`/FTS across three
  small tables is enough for one user (YAGNI).
- Fuzzy/typo tolerance, ranking tuning, highlights beyond a basic match.
- Searching chat message history (separate concern; add later if wanted).

## 3. Design

- `pages/search/models.py`: `search(q)` runs a query per table —
  events (`title`/`location`/`notes`), todos (`title`/`notes`), notes (`text`,
  reusing Spec I's FTS index) — each `ILIKE %q%` (notes via FTS), capped per group.
- `routes.py`: `GET /api/search` + a `/search` page template.
- Tool: `search_all` {`query`} → `search(q)` result, for voice/agent.

No new tables; composes existing models.

## 4. Testing

- Unit: `search(q)` matches across all three sources; empty groups omitted/empty.
- Unit: per-group cap respected; `/api/search` returns the structure.
- Unit: `search_all` tool wraps the same function.

## 5. Risks

- **Performance** — trivial at personal scale; add per-column indexes only if
  needed.
- **Overlap with `recall`** — `recall` (Spec I) is notes-only; `search_all` is the
  cross-entity superset. Keep both; the agent picks by intent.
