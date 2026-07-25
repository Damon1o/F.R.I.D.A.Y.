# F.R.I.D.A.Y. — Web Search Tool Design (Spec H)

**Date:** 2026-07-24
**Status:** Draft (design).
**Depends on:** Spec A (agent tool loop).

## 1. Context

The DeepSeek agent can only answer from training data. A `search_web` tool lets
FRIDAY answer current-fact questions ("who won last night", "opening hours") by
fetching top results and letting the LLM summarise them in-loop.

## 2. Goals / Non-goals

**Goals**
- `search_web(query)` tool → a small list of `{title, url, snippet}`.
- One provider behind a thin wrapper, key in env.
- Result set small (default 5) to keep the tool-result token cost low.

**Non-goals**
- Full page fetching/scraping/reading (a separate `fetch_url` tool could come
  later; not now — YAGNI).
- A search UI in the app. Tool-only, invoked by the agent.
- Multiple providers / fallback ranking.

## 3. Design

**Provider:** a keyed JSON search API (Brave Search API or Tavily — both have a
free tier and a clean JSON response; pick in the plan). Wrapper isolates it so
the choice is swappable.

**Tool** (add to `TOOLS` + `dispatch`):
- `search_web` {`query`: string, `count`?: int=5} →
  `[{title, url, snippet}]`, truncated to `count`.

**Module** `pages/friday/search.py` — `requests` GET, map response to the shape.
Key from env: `SEARCH_API_KEY`. Missing key → `{"error": "search unavailable"}`.

**Prompt note:** extend the agent system prompt so the LLM cites/uses results and
doesn't invent URLs.

## 4. Testing

- Unit: map a canned provider JSON to `[{title,url,snippet}]`, respect `count`.
- Unit: missing key → graceful error, no raise.

## 5. Risks

- **Cost/rate limits** — small `count`, and it's single-user; monitor. Free tier
  likely sufficient.
- **Prompt-injection via results** — results are data, not instructions; system
  prompt tells the model to treat snippets as untrusted. No tool auto-executes
  from snippet content.
