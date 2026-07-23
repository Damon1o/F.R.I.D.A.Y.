# Kiko — project instructions

## Always
- **RTK**: route dev/CLI operations through RTK (Rust Token Killer) for token savings.
  Active via the global `PreToolUse` Bash hook — do not bypass it.
- **Ponytail**: apply the `ponytail` skill (laziest solution that works — YAGNI,
  stdlib/native before dependencies, one line before fifty) to every coding task:
  writing, adding, refactoring, fixing, reviewing code, and choosing dependencies.

## Design rules (hard)
- No emojis / Unicode glyph icons. All icons via self-hosted, pinned **Lucide**.
- No external CDN: self-host fonts (**Hanken Grotesk**) and all assets. Zero external
  network requests from the app.
- Monochrome, glass design system sourced from the Stitch export
  (`docs/design/stitch/`); tokens in `static/css/tokens.css`, no hex literals in
  component CSS.

## Stack
Flask app-factory + server-rendered Jinja + vanilla JS `fetch`, SQLite via stdlib
`sqlite3`. No build step, no SPA. Single user, binds `127.0.0.1`. See
`docs/superpowers/specs/2026-07-21-phase1-core-design.md`.

## Clarification
- Feel free to ask questions if unsure about any task, requirement, or implementation detail.
