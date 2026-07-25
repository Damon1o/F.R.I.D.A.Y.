# F.R.I.D.A.Y. — Email Tool Design (Spec M)

**Date:** 2026-07-24
**Status:** Draft (design). **Sensitive — read/draft first, send gated.**
**Depends on:** Spec A.

## 1. Context

Let FRIDAY triage mail: "read my unread", "draft a reply to Kate". Gmail is the
provider. This is the most **sensitive** tool in the set — it reads private mail
and can send on the user's behalf — so it is scoped conservatively: read and
**draft** freely, **send behind an explicit confirmation**.

## 2. Goals / Non-goals

**Goals**
- `list_unread(count?)`, `read_thread(id)`, `draft_reply(thread_id, body)`,
  `search_mail(query)` tools.
- `send_email` exists but requires an explicit user confirm step (never
  auto-sent inside a tool loop).
- OAuth via Google, tokens persisted in `settings` (same pattern as Spotify).

**Non-goals**
- Attachments, labels management, filters (draft/read/search is the 80%).
- Auto-reply / autonomous sending. A human always confirms a send.
- Multiple accounts.

## 3. Design

**Auth:** Google OAuth2 (Gmail API, scopes `gmail.readonly` + `gmail.compose`;
`gmail.send` only if send is enabled). Tokens in `settings`
(`gmail_access_token`/`gmail_refresh_token`), refresh on expiry — mirror the
existing `SpotifyProvider` token-persistence design.

**Module** `pages/mail/` — a `GmailProvider` (list/get/search/create_draft/send)
wrapping the Gmail REST API via `requests`.

**Tools** (add to `TOOLS` + `dispatch`):
- read/draft/search return data or a draft id.
- `send_email` does **not** live in the auto-executed tool set by default; instead
  the agent returns a proposed send as an `action` the UI surfaces with a
  Confirm button that calls a dedicated `POST /api/mail/send/<draft_id>`.

## 4. Security (this spec's core concern)

- **Send requires explicit human confirm** — no send inside `run_text`/voice loop.
- **Scopes minimal** — read + compose; add send scope only when the user opts in.
- **Tokens** never in source; `settings`-persisted; refresh handled server-side.
- **Prompt-injection:** email bodies are untrusted; the system prompt forbids the
  agent from acting on instructions found inside emails (no tool auto-fires from
  message content).
- **Redaction:** tool results to the LLM include only necessary fields.

## 5. Testing

- Unit: provider maps Gmail JSON → `{from, subject, snippet, thread_id}`; token
  refresh path (faked HTTP).
- Unit: `send_email` is NOT auto-dispatchable; the confirm endpoint sends exactly
  the named draft.
- Unit: injection guard — a tool result containing "delete all events" does not
  cause a tool call (agent-loop test with faked LLM).

## 6. Risks

- **Highest-blast-radius tool** — mitigated by read/draft-only default and the
  confirm-gated send.
- **Google OAuth verification** for restricted Gmail scopes may require app review
  — note in plan; test mode covers the single user meanwhile.
