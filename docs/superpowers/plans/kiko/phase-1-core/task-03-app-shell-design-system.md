# Kiko Phase 1 (Core) — Task 03 Plan: App Shell + Design System

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute top-to-bottom; do not skip the "run it and watch it fail" steps.

**Goal:** Recover the glassmorphism design system from git history and stand up the Kiko app shell — a `base.html` template with a topbar, an icon-only Lucide sidebar (links to `/`, `/calendar`, `/todos`), and a persistent light/dark theme toggle — smoke-tested through a temporary `/` route.

**Architecture:** Server-rendered Jinja + vanilla JS, no build step. `tokens.css` (design tokens) and `depth.css` (glass/neu utilities) are restored verbatim from commit `bb6176f`. A new `app.css` supplies only the shell layout (grid: topbar + icon sidebar + content). `theme.js` sets `data-theme` on `<html>` and persists the choice to `localStorage`. Lucide icons are self-hosted (inlined SVG for `currentColor` theming); a vendor `README.md` documents the pinned version. `app.py` gains a temporary `/` route that renders `base.html` so the shell is testable now; Task 08 replaces it with the dashboard blueprint.

**Tech Stack:** Python 3, Flask (app-factory pattern), Jinja2, vanilla CSS/JS, pytest.

## Global Constraints (apply to every step)

- Python 3, Flask app-factory pattern. Server-rendered Jinja + vanilla JS `fetch`. **NO build step, NO frontend framework.**
- Single user, localhost. **NO auth, NO sessions/login.**
- **Icons:** self-hosted, pinned Lucide SVG only. **NO CDN. NO emojis / NO Unicode pictographic glyphs anywhere in the UI.**
- Reuse the glassmorphism design system from git history (`git show bb6176f:...`); do not hand-rewrite tokens.
- **TDD:** write the failing test first, run it (see it fail), implement minimal code, run it (see it pass), commit. Small, frequent commits.
- DRY, YAGNI. No search bar, avatars, or other HR-mockup chrome — Kiko's topbar is brand + theme toggle only.
- All datetimes (elsewhere in the app) are ISO-8601 UTC text; persistence is stdlib `sqlite3` only. (Not exercised by this task, but honored project-wide.)

---

### Task 03: App shell: base template + glassmorphism design system + Lucide

**Files:**
- Create: `static/css/tokens.css` (recovered verbatim from `bb6176f`)
- Create: `static/css/depth.css` (recovered verbatim from `bb6176f`)
- Create: `static/css/app.css` (new — shell layout only)
- Create: `static/js/theme.js` (new — theme toggle + persistence)
- Create: `static/vendor/lucide/README.md` (new — pinned-version + self-host note)
- Create: `templates/base.html` (recovered from `bb6176f` as a starting point, then adapted)
- Create: `tests/test_shell.py` (new — shell smoke test)
- Modify: `app.py` — add a temporary `/` index route inside `create_app()` that renders `base.html`

**Interfaces:**
- Consumes: `create_app(test_config: dict | None = None) -> Flask` from Task 01 (config keys `DATABASE`, `SECRET_KEY`; registers blueprints; calls `db.init_app(app)`).
- Produces (later tasks rely on these exact artifacts):
  - `templates/base.html` — Jinja blocks `title`, `content`, `page_scripts`; topbar + icon-only sidebar shell; theme toggle. Sidebar nav links use literal hrefs `/`, `/calendar`, `/todos` (blueprint endpoints do not exist yet). Sets active state from an optional `active_page` template variable (`"dashboard"` | `"calendar"` | `"todos"`).
  - `static/css/tokens.css` — design tokens: `--bg-canvas`, `--bg-surface`, `--text-primary`, `--text-secondary`, `--accent`, `--accent-hover`, `--accent-light`, `--glass-bg`, `--glass-bg-strong`, `--glass-border`, `--radius-*`, `--space-*`, `--text-*`, `--font-body`, `--font-display`, `--duration-*`, `--ease-*`, `--z-*`, `--focus-ring`; light default on `:root`, dark under `[data-theme="dark"]`.
  - `static/css/depth.css` — glass/neu utility classes (`.glass`, `.glass-card`, `.neu-*`, `.elev-*`, focus-ring + animation utilities).
  - `static/css/app.css` — shell layout classes: `.app-layout`, `.top-bar`, `.brand`, `.theme-toggle`, `.sidebar`, `.nav-item`, `.content-area`.
  - `static/js/theme.js` — reads/writes `localStorage` key `"kiko-theme"`, sets `data-theme` on `document.documentElement`, wires the `[data-theme-toggle]` button.
  - `GET /` — temporary route returning `render_template("base.html", active_page="dashboard")` (Task 08 replaces this).

---

- [ ] **Step 1: Create the directory tree and recover `tokens.css` verbatim from history**

Run in a Bash / Git-Bash shell (use bash, not PowerShell, so the redirect writes UTF-8 without a BOM):

```bash
mkdir -p static/css static/js static/vendor/lucide templates tests
git show bb6176f:static/css/tokens.css > static/css/tokens.css
```

Verify the recovery — the file must be the OKLCH token set (warm-slate neutrals + amber accent, light `:root` / dark `[data-theme="dark"]`, glass + shadow + spacing + type scale tokens):

```bash
head -n 5 static/css/tokens.css
grep -c -- "--accent" static/css/tokens.css   # expect a non-zero count
```

Do NOT edit this file — it is used verbatim.

- [ ] **Step 2: Recover `depth.css` verbatim from history**

```bash
git show bb6176f:static/css/depth.css > static/css/depth.css
```

Verify it contains the glass/neu utility classes:

```bash
grep -E "\.glass|\.neu-raised|\.elev-1" static/css/depth.css   # expect matches
```

Do NOT edit this file — it is used verbatim. (It references a `layout.css` in a comment; that file is intentionally absent. `app.css`, created below, supplies the shell layout instead.)

- [ ] **Step 3: Load the design skill and confirm reuse of the recovered tokens (design prep, no file change)**

Before writing any markup or `app.css`, invoke the **frontend-design** skill (`Skill: frontend-design`) and skim the **glassmorphism-design-system** skill for reference. Design constraints for this shell:

- Reuse ONLY the recovered tokens/utilities — never hard-code colors, radii, spacing, or shadows; reference `var(--…)` from `tokens.css` and classes from `depth.css`.
- Sidebar is **icon-only** (compact rail), topbar carries the brand mark + theme toggle. No search bar, no avatars (those were HR-mockup chrome; YAGNI here).
- Icons are **self-hosted Lucide SVG, inlined** so they inherit `currentColor` in light/dark. **Never** an emoji, a Unicode symbol/dingbat, or a CDN `<script>`/`<link>`.
- Confirm the exact token names you will use exist in `static/css/tokens.css`:

```bash
grep -E -- "--bg-canvas|--glass-bg-strong|--glass-border|--accent-light|--radius-lg|--space-6|--z-sticky|--font-display" static/css/tokens.css
```

Expected: every name above prints at least once. These are the tokens `app.css` and `base.html` depend on.

- [ ] **Step 4: Write the failing shell smoke test**

Create `tests/test_shell.py` with this exact content:

```python
"""Smoke tests for the app shell (Task 03).

The temporary `/` route renders base.html so we can verify the shell markup
before the dashboard blueprint (Task 08) exists.
"""
import re

import pytest

from app import create_app

# Match common emoji / pictographic / dingbat / arrow glyph ranges. The shell
# is authored entirely in ASCII + inline Lucide SVG (also ASCII), so any hit
# here means a banned glyph slipped into the UI.
EMOJI_RE = re.compile(
    "["
    "\U00002190-\U000021FF"  # arrows
    "\U00002300-\U000023FF"  # misc technical (e.g. hourglass, keyboard)
    "\U00002500-\U000027BF"  # box drawing, misc symbols, dingbats
    "\U0000FE00-\U0000FE0F"  # variation selectors (emoji presentation)
    "\U0001F000-\U0001FAFF"  # emoji, pictographs, symbols & pictographs ext.
    "]"
)


@pytest.fixture
def client():
    app = create_app({"DATABASE": ":memory:", "SECRET_KEY": "test"})
    app.config["TESTING"] = True
    return app.test_client()


def test_index_returns_200(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_shell_has_sidebar_nav_links(client):
    html = client.get("/").get_data(as_text=True)
    assert 'href="/calendar"' in html
    assert 'href="/todos"' in html
    assert 'href="/"' in html


def test_shell_has_theme_toggle(client):
    html = client.get("/").get_data(as_text=True)
    assert "data-theme-toggle" in html


def test_shell_has_no_emoji(client):
    html = client.get("/").get_data(as_text=True)
    match = EMOJI_RE.search(html)
    assert match is None, f"banned glyph in shell: {match.group()!r}"
```

- [ ] **Step 5: Run the test and watch it fail**

```bash
pytest tests/test_shell.py -v
```

Expected: FAIL. There is no `/` route yet (Task 01 registered only the temporary `/healthz`), so `test_index_returns_200` fails with `assert 404 == 200`, and the other three fail because the response body is Flask's 404 page rather than the shell markup.

- [ ] **Step 6: Create `static/js/theme.js`**

Create `static/js/theme.js` with this exact content. It is loaded as a blocking `<script>` in `<head>` so `data-theme` is set before first paint (no flash), then wires the toggle on `DOMContentLoaded`:

```javascript
/* Kiko theme toggle — sets data-theme on <html> and persists to localStorage.
   Loaded (blocking) in <head> so the stored theme applies before first paint. */
(function () {
  "use strict";
  var STORAGE_KEY = "kiko-theme";
  var root = document.documentElement;

  function stored() {
    try {
      return window.localStorage.getItem(STORAGE_KEY);
    } catch (e) {
      return null;
    }
  }

  function persist(theme) {
    try {
      window.localStorage.setItem(STORAGE_KEY, theme);
    } catch (e) {
      /* private mode / storage disabled — theme still applies for this page */
    }
  }

  function preferred() {
    return window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  function apply(theme) {
    root.setAttribute("data-theme", theme);
  }

  // Apply immediately (html element exists during head parsing).
  apply(stored() || preferred());

  document.addEventListener("DOMContentLoaded", function () {
    var toggle = document.querySelector("[data-theme-toggle]");
    if (!toggle) {
      return;
    }
    toggle.addEventListener("click", function () {
      var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      apply(next);
      persist(next);
    });
  });
})();
```

- [ ] **Step 7: Create `static/css/app.css` (shell layout only)**

Create `static/css/app.css` with this exact content. It references only tokens from `tokens.css` and assumes `tokens.css` + `depth.css` are linked first:

```css
/* ==========================================================================
   Kiko app shell — topbar + icon sidebar + content area.
   Requires tokens.css and depth.css to be linked first (base.html does this).
   ========================================================================== */

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: var(--font-body);
  background: var(--bg-canvas);
  color: var(--text-primary);
  -webkit-font-smoothing: antialiased;
}

/* ===== Layout grid ===== */
.app-layout {
  display: grid;
  grid-template-areas:
    "topbar topbar"
    "sidebar content";
  grid-template-rows: 64px 1fr;
  grid-template-columns: 72px 1fr;
  min-height: 100vh;
  background: var(--bg-canvas);
}

/* ===== Topbar ===== */
.top-bar {
  grid-area: topbar;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 64px;
  padding: 0 var(--space-6);
  background: var(--glass-bg);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border-bottom: 1px solid var(--glass-border);
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  text-decoration: none;
  color: var(--text-primary);
}

.brand-mark {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, var(--accent), var(--accent-hover));
  flex-shrink: 0;
}

.brand-text {
  font-family: var(--font-display);
  font-size: var(--text-lg);
  font-weight: var(--font-weight-bold);
  white-space: nowrap;
}

/* ===== Theme toggle ===== */
.theme-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: var(--radius-full);
  border: 1px solid var(--border-default);
  background: var(--bg-surface);
  color: var(--text-secondary);
  cursor: pointer;
  transition: color var(--duration-fast) var(--ease-out-quart),
    border-color var(--duration-fast) var(--ease-out-quart);
}

.theme-toggle:hover {
  color: var(--accent);
  border-color: var(--accent);
}

.theme-toggle svg {
  width: 20px;
  height: 20px;
}

/* Show the sun in light mode, the moon in dark mode. */
.theme-toggle .icon-moon {
  display: none;
}

[data-theme="dark"] .theme-toggle .icon-sun {
  display: none;
}

[data-theme="dark"] .theme-toggle .icon-moon {
  display: inline-flex;
}

/* ===== Icon sidebar ===== */
.sidebar {
  grid-area: sidebar;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-2);
  background: var(--glass-bg-strong);
  backdrop-filter: blur(24px) saturate(200%);
  -webkit-backdrop-filter: blur(24px) saturate(200%);
  border-right: 1px solid var(--glass-border);
  position: sticky;
  top: 64px;
  height: calc(100vh - 64px);
}

.nav-item {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: var(--radius-lg);
  color: var(--text-secondary);
  text-decoration: none;
  transition: background var(--duration-fast) var(--ease-out-cubic),
    color var(--duration-fast) var(--ease-out-cubic);
}

.nav-item:hover {
  background: var(--bg-surface-hover);
  color: var(--text-primary);
}

.nav-item.active {
  background: var(--accent-light);
  color: var(--accent);
}

.nav-item svg {
  width: 22px;
  height: 22px;
}

/* ===== Content ===== */
.content-area {
  grid-area: content;
  padding: var(--space-6);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}
```

- [ ] **Step 8: Create `static/vendor/lucide/README.md` (pinned Lucide, self-host note)**

Create `static/vendor/lucide/README.md` with this exact content:

```markdown
# Lucide icons (self-hosted, pinned)

Kiko uses [Lucide](https://lucide.dev) icons. Per project rule, icons are
**self-hosted** — never loaded from a CDN — and **emojis / Unicode pictographs
are banned** anywhere in the UI.

## Pinned version

- **Lucide `0.544.0`** (ISC license — see https://github.com/lucide-icons/lucide).
- Pin this exact version. When upgrading, bump it here in one place and re-copy
  any changed icon markup.

## How icons are embedded

The icons are **inlined as `<svg>` markup** directly in `templates/base.html`
(and other page templates) rather than referenced as external files. Inlining is
required so each icon inherits `currentColor`, letting it recolor with the
active light/dark theme. Every inlined icon uses Lucide's canonical wrapper:

    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
         viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="2" stroke-linecap="round" stroke-linejoin="round"> … </svg>

## Icons currently used

| Icon               | Where            | Purpose            |
| ------------------ | ---------------- | ------------------ |
| `layout-dashboard` | sidebar          | Dashboard (`/`)    |
| `calendar`         | sidebar          | Calendar (`/calendar`) |
| `list-todo`        | sidebar          | To-Do (`/todos`)   |
| `sun`              | topbar toggle    | light-mode state   |
| `moon`             | topbar toggle    | dark-mode state    |

## Adding or updating an icon

1. Find the icon at https://lucide.dev/icons at the pinned version.
2. Copy the `<svg>…</svg>` markup from the pinned release
   (`node_modules/lucide-static/icons/<name>.svg`, or the GitHub tag) — **not**
   from a CDN.
3. Paste it inline where needed, keeping the wrapper attributes above so it
   themes with `currentColor`. Add a row to the table.
```

- [ ] **Step 9: Recover `base.html` from history, then create the adapted shell template**

First recover the historical template as a reference starting point:

```bash
git show bb6176f:templates/base.html > templates/base.html
```

The recovered file targets the old HR app: it links `dashboard.css` + `chat-widget.js`, uses `url_for('dashboard.dashboard_page')` / `url_for('calendar.calendar_page')` endpoints (which do NOT exist yet and would raise `BuildError`), exposes blocks `title`/`extra_css`/`content`/`scripts`, and has a text sidebar with a search bar + avatar. **Replace its entire contents** with the adapted Kiko shell below — literal hrefs, the contract's block names (`title`/`content`/`page_scripts`), inline Lucide SVGs, and the theme toggle. Overwrite `templates/base.html` with exactly:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Kiko{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/tokens.css') }}">
  <link rel="stylesheet" href="{{ url_for('static', filename='css/depth.css') }}">
  <link rel="stylesheet" href="{{ url_for('static', filename='css/app.css') }}">
  <script src="{{ url_for('static', filename='js/theme.js') }}"></script>
</head>
<body>
  <div class="app-layout">
    <header class="top-bar">
      <a href="/" class="brand">
        <span class="brand-mark"></span>
        <span class="brand-text">Kiko</span>
      </a>
      <button type="button" class="theme-toggle" data-theme-toggle aria-label="Toggle color theme">
        <svg class="icon-sun" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4"/>
          <path d="M12 2v2"/>
          <path d="M12 20v2"/>
          <path d="m4.93 4.93 1.41 1.41"/>
          <path d="m17.66 17.66 1.41 1.41"/>
          <path d="M2 12h2"/>
          <path d="M20 12h2"/>
          <path d="m6.34 17.66-1.41 1.41"/>
          <path d="m19.07 4.93-1.41 1.41"/>
        </svg>
        <svg class="icon-moon" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>
        </svg>
      </button>
    </header>
    <nav class="sidebar" aria-label="Primary">
      <a href="/" class="nav-item {{ 'active' if active_page == 'dashboard' else '' }}" aria-label="Dashboard" title="Dashboard">
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <rect width="7" height="9" x="3" y="3" rx="1"/>
          <rect width="7" height="5" x="14" y="3" rx="1"/>
          <rect width="7" height="9" x="14" y="12" rx="1"/>
          <rect width="7" height="5" x="3" y="16" rx="1"/>
        </svg>
      </a>
      <a href="/calendar" class="nav-item {{ 'active' if active_page == 'calendar' else '' }}" aria-label="Calendar" title="Calendar">
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M8 2v4"/>
          <path d="M16 2v4"/>
          <rect width="18" height="18" x="3" y="4" rx="2"/>
          <path d="M3 10h18"/>
        </svg>
      </a>
      <a href="/todos" class="nav-item {{ 'active' if active_page == 'todos' else '' }}" aria-label="To-Do" title="To-Do">
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <rect x="3" y="5" width="6" height="6" rx="1"/>
          <path d="m3 17 2 2 4-4"/>
          <path d="M13 6h8"/>
          <path d="M13 12h8"/>
          <path d="M13 18h8"/>
        </svg>
      </a>
    </nav>
    <main class="content-area">
      {% block content %}{% endblock %}
    </main>
  </div>
  {% block page_scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 10: Add the temporary `/` index route in `app.py`**

The route must live **inside** `create_app()` so it is registered on the returned app. Make two edits:

1. Ensure `render_template` is imported. The existing Flask import (from Task 01) likely reads `from flask import Flask`. Change it to:

```python
from flask import Flask, render_template
```

2. Inside `create_app()`, add the temporary index route. Place it next to the existing temporary `/healthz` route (added in Task 01), just before `return app`:

```python
    @app.route("/")
    def index():
        # Temporary shell smoke-test route. Task 08 replaces this with the
        # dashboard blueprint (GET / -> today's events + open todos + chat FAB).
        return render_template("base.html", active_page="dashboard")
```

Leave the `/healthz` route and everything else in `create_app()` unchanged.

- [ ] **Step 11: Run the test and watch it pass**

```bash
pytest tests/test_shell.py -v
```

Expected: PASS — all four tests green (`test_index_returns_200`, `test_shell_has_sidebar_nav_links`, `test_shell_has_theme_toggle`, `test_shell_has_no_emoji`).

If `test_shell_has_no_emoji` fails, an emoji or Unicode glyph slipped into the markup — replace it with an inlined Lucide SVG. If `test_index_returns_200` errors with `BuildError`, a `url_for('<blueprint>.<endpoint>')` call was left in `base.html`; the nav/brand links must be literal hrefs (`/`, `/calendar`, `/todos`).

- [ ] **Step 12: Commit**

```bash
git add static/css/tokens.css static/css/depth.css static/css/app.css \
        static/js/theme.js static/vendor/lucide/README.md \
        templates/base.html tests/test_shell.py app.py
git commit -m "feat: add app shell with glassmorphism design system, icon sidebar, and theme toggle"
```

---

## Self-review checklist (run after executing, before handing off)

- **Contract match:** `base.html` exposes blocks `title` / `content` / `page_scripts` (not the historical `extra_css`/`scripts`); sidebar has literal `href="/"`, `href="/calendar"`, `href="/todos"`; a `[data-theme-toggle]` element exists. ✅ verify by re-reading the template.
- **No CDN / no emoji:** `grep -rE "cdn|googleapis|unpkg|jsdelivr" templates/ static/` returns nothing; `pytest tests/test_shell.py::test_shell_has_no_emoji` is green.
- **Tokens reused, not rewritten:** `tokens.css` and `depth.css` are byte-for-byte from `bb6176f` (`git diff bb6176f -- static/css/tokens.css static/css/depth.css` shows no changes).
- **Theme persistence:** `theme.js` writes `localStorage["kiko-theme"]` and sets `data-theme` on `<html>`; loaded blocking in `<head>` to avoid a flash of the wrong theme.
- **Temporary route flagged:** the `/` route in `app.py` carries the "Task 08 replaces this" comment.
