# F.R.I.D.A.Y. — project instructions

## Always
- **RTK**: route dev/CLI operations through RTK (Rust Token Killer) for token savings.
  Active via the global `PreToolUse` Bash hook — do not bypass it.
- **i-have-adhd**: apply the `i-have-adhd` skill (`.agents/skills/i-have-adhd/`) to every
  response — lead with the next action, number multi-step work, restate state across turns,
  suppress tangents, give specific time estimates. Stays on for the whole session. **Always invoke this skill.**
- **Ponytail**: apply the `ponytail` skill (laziest solution that works — YAGNI,
  stdlib/native before dependencies, one line before fifty) to every coding task:
  writing, adding, refactoring, fixing, reviewing code, and choosing dependencies.
- **Design Taste**: when designing webpages or UI, always invoke the `design-taste-frontend` skill (`~/.agents/skills/design-taste-frontend/`) for distinctive, production-grade interfaces.

## Design rules (hard)
- No emojis / Unicode glyph icons. All icons via self-hosted, pinned **Lucide**.
- No external CDN: self-host fonts (**Hanken Grotesk**) and all assets. Zero external
  network requests from the app.
- Monochrome, glass design system sourced from the Stitch export
  (`docs/design/stitch/`); tokens in `static/css/tokens.css`, no hex literals in
  component CSS.

## Stack
Flask app-factory + server-rendered Jinja + vanilla JS `fetch`, Postgres (Neon)
via psycopg 3. Deployed on Vercel serverless (`api/index.py` WSGI entrypoint);
secrets via Vercel env. No build step, no SPA. Single user. See
`docs/superpowers/specs/2026-07-23-cloud-migration-design.md`.

## Clarification
- Feel free to ask questions if unsure about any task, requirement, or implementation detail.
