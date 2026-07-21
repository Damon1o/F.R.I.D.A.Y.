# Dashboard Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the bare-bones layout with a polished dashboard/calendar frontend matching `image.png`, reusing the `hr-dashboard/` design system, with chat moved from a persistent aside into a reusable widget (dashboard card + calendar FAB).

**Architecture:** Static CSS design tokens + depth utilities copied verbatim from `hr-dashboard/`; a new `dashboard.css` holds layout/card/chat-widget classes trimmed to what this app needs. A new `dashboard_bp` Flask blueprint serves `/` with static placeholder cards plus one real chat widget. The existing `calendar_bp` keeps its routes but the template/JS are restyled and gain a floating chat button. Chat JS is refactored into one reusable factory (`createChatWidget`) instantiated twice instead of duplicated.

**Tech Stack:** Flask + Jinja2, vanilla JS (no framework), plain CSS with custom properties (no build step).

## Global Constraints

- No new backend models, migrations, or routes beyond the one new `dashboard_bp` page route — Planned Absences / Future Events / Onboarding cards are static Jinja markup, not DB-backed.
- No authentication/user-profile system — any user avatar/name shown is decorative placeholder text.
- `/api/chat` response shape is `{ reply, input_tokens, output_tokens, total_tokens, budget_warning }` (flat, not nested under `usage`) — every consumer must read these top-level fields.
- `/calendar/api/events` requires both `start` and `end` query params (ISO-8601) or the backend raises — every caller must always pass both.
- Keep the existing `escapeHtml()` XSS guard on any event title rendered into the DOM via `innerHTML`.
- No new JS dependencies/build step — reuse `hr-dashboard/*.css` content directly, vanilla JS only.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `static/css/tokens.css` | create | Copy of `hr-dashboard/tokens.css` (colors, spacing, type, motion, radius, z-index) |
| `static/css/depth.css` | create | Copy of `hr-dashboard/depth.css` (glass/neu utility classes, elevation scale) |
| `static/css/dashboard.css` | create | App shell (topbar/sidebar/content grid), `.card` family, chat widget, dashboard placeholder cards |
| `static/css/style.css` | rewrite | Calendar month-grid only (day cells, event pills), rebased on tokens |
| `templates/base.html` | rewrite | App shell markup: topbar, sidebar nav, content block. No chat aside. |
| `templates/dashboard.html` | create (Task 3, placeholder), replace (Task 5, real content) | Planned Absences / Future Events / Onboarding / chat card |
| `templates/calendar.html` | rewrite | Full-width calendar card + FAB chat button |
| `static/js/chat-widget.js` | create | `createChatWidget(container, options)` factory, replaces `chat.js` |
| `static/js/chat.js` | delete | Superseded by `chat-widget.js` |
| `static/js/dashboard.js` | create | Mounts `#dash-chat` widget, wires quick-action chips |
| `static/js/calendar.js` | rewrite | Fix `/calendar/api/events` endpoint + query params, render into new markup, mount FAB widget on click |
| `pages/dashboard/__init__.py` | create (Task 3) | Empty package marker (matches `pages/calendar/__init__.py`) |
| `pages/dashboard/routes.py` | create (Task 3) | `dashboard_bp` with `GET /` |
| `app.py` | modify (Task 3) | Register `dashboard_bp` |
| `tests/test_dashboard.py` | create (Task 3, minimal), strengthen (Task 5) | Route + markup assertions |
| `tests/test_calendar_routes.py` | modify | Keep passing — endpoint contract unchanged, only add FAB markup assertion |

---

### Task 1: Copy design tokens and depth CSS

**Files:**
- Create: `static/css/tokens.css`
- Create: `static/css/depth.css`

**Interfaces:**
- Produces: CSS custom properties (`--bg-canvas`, `--text-primary`, `--accent`, `--space-*`, `--radius-*`, `--shadow-*`, `--duration-*`, `--ease-*`, etc.) and utility classes (`.glass`, `.glass-card`, `.card-hover`... via `depth.css`) consumed by every later CSS/HTML task.

- [ ] **Step 1: Copy `hr-dashboard/tokens.css` to `static/css/tokens.css`**

Run:
```bash
cp "hr-dashboard/tokens.css" "static/css/tokens.css"
```

- [ ] **Step 2: Copy `hr-dashboard/depth.css` to `static/css/depth.css`, fix its import path**

Run:
```bash
cp "hr-dashboard/depth.css" "static/css/depth.css"
```

`depth.css` has no `@import` (it only defines classes/vars), so no edit needed — verify:

```bash
grep -n "@import" static/css/depth.css
```

Expected: no output (no import lines).

- [ ] **Step 3: Verify both files are valid CSS (no syntax errors) by checking brace balance**

Run:
```bash
node -e "
const fs=require('fs');
for (const f of ['static/css/tokens.css','static/css/depth.css']) {
  const s=fs.readFileSync(f,'utf8');
  const open=(s.match(/\{/g)||[]).length;
  const close=(s.match(/\}/g)||[]).length;
  console.log(f, open, close, open===close ? 'OK' : 'MISMATCH');
}
"
```

Expected: both lines end with `OK`.

- [ ] **Step 4: Commit**

```bash
git add static/css/tokens.css static/css/depth.css
git commit -m "Add design tokens and depth CSS copied from hr-dashboard"
```

---

### Task 2: Dashboard shell + card CSS (`dashboard.css`)

**Files:**
- Create: `static/css/dashboard.css`

**Interfaces:**
- Consumes: custom properties from `tokens.css` (Task 1).
- Produces: `.app-layout`, `.top-bar`, `.sidebar`, `.nav-item`, `.logo`, `.content-area`, `.card` family, `.leave-block`, `.employee-cell`/`.employee-avatar`/`.employee-name`/`.employee-role`, `.event-card` family, `.onboarding-row`, `.chat-card`, `.chat-header`, `.chat-messages`, `.chat-message`, `.message-avatar`, `.message-content`, `.chat-input-area`, `.ai-welcome`, `.ai-orb`, `.ai-quick-actions`, `.quick-action-btn`, `.fab-chat-button`, `.fab-chat-panel` — all consumed by `base.html`, `dashboard.html`, `calendar.html` (Tasks 3-6).

- [ ] **Step 1: Write `static/css/dashboard.css`**

```css
/* ==========================================================================
   Dashboard CSS — app shell, cards, chat widget
   Requires tokens.css and depth.css to be linked first (base.html does this).
   ========================================================================== */

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: var(--font-body);
  background: var(--bg-canvas);
  color: var(--text-primary);
}

/* ===== App Shell ===== */
.app-layout {
  display: grid;
  grid-template-areas:
    "topbar topbar"
    "sidebar content";
  grid-template-rows: 64px 1fr;
  grid-template-columns: 240px 1fr;
  min-height: 100vh;
  background: var(--bg-canvas);
}

.top-bar {
  grid-area: topbar;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 64px;
  padding: 0 var(--space-6);
  background: var(--glass-bg);
  backdrop-filter: blur(20px);
  border-bottom: 1px solid var(--glass-border);
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
}

.top-bar-left, .top-bar-right {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.logo {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-lg);
}

.logo-mark {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, var(--accent), var(--accent-hover));
}

.logo-text {
  font-family: var(--font-display);
  font-size: var(--text-lg);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
  white-space: nowrap;
}

.global-search {
  position: relative;
  width: 100%;
  max-width: 320px;
}

.search-input {
  width: 100%;
  padding: var(--space-2) var(--space-4);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-full);
  background: var(--bg-surface);
  color: var(--text-primary);
  font: inherit;
  font-size: var(--text-sm);
}

.search-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: var(--focus-ring);
}

.user-avatar-placeholder {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-full);
  background: linear-gradient(135deg, var(--color-accent-300), var(--color-accent-500));
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent-foreground);
  font-size: var(--text-sm);
  font-weight: var(--font-weight-semibold);
}

/* ===== Sidebar ===== */
.sidebar {
  grid-area: sidebar;
  display: flex;
  flex-direction: column;
  background: var(--glass-bg-strong);
  backdrop-filter: blur(24px);
  border-right: 1px solid var(--glass-border);
  padding: var(--space-3) var(--space-2);
  position: sticky;
  top: 64px;
  height: calc(100vh - 64px);
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  width: 100%;
  padding: var(--space-3);
  border-radius: var(--radius-lg);
  color: var(--text-secondary);
  text-decoration: none;
  font-size: var(--text-sm);
  font-weight: var(--font-weight-medium);
  transition: all var(--duration-fast) var(--ease-out-cubic);
}

.nav-item:hover {
  background: var(--bg-surface-hover);
  color: var(--text-primary);
}

.nav-item.active {
  background: var(--accent-light);
  color: var(--accent);
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

/* ===== Card ===== */
.card {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  overflow: hidden;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--border-subtle);
}

.card-title {
  font-size: var(--text-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.card-content {
  padding: var(--space-5);
}

.dashboard-cards-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-4);
}

@media (max-width: 960px) {
  .dashboard-cards-row {
    grid-template-columns: 1fr;
  }
}

/* ===== Planned Absences (placeholder) ===== */
.employee-cell {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-5);
  border-bottom: 1px solid var(--border-subtle);
}

.employee-cell:last-child {
  border-bottom: none;
}

.employee-avatar {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-full);
  background: var(--color-neutral-200);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--text-secondary);
  flex-shrink: 0;
}

.employee-name {
  font-size: var(--text-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.employee-role {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.employee-info {
  flex: 1;
  min-width: 0;
}

.leave-block {
  border-radius: var(--radius-full);
  padding: var(--space-1) var(--space-3);
  font-size: var(--text-xs);
  font-weight: var(--font-weight-medium);
  color: white;
  white-space: nowrap;
}

.leave-block.paid-leave { background: linear-gradient(135deg, #A764FF, #7D4DFF); }
.leave-block.vacation { background: linear-gradient(135deg, #36D98D, #17C96B); }
.leave-block.sick-leave { background: linear-gradient(135deg, #4D8EFF, #3B7DD8); }

/* ===== Future Events (placeholder) ===== */
.event-card {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
}

.event-card:not(:last-child) {
  border-bottom: 1px solid var(--border-subtle);
}

.event-card-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-lg);
  flex-shrink: 0;
  background: linear-gradient(135deg, #4D8EFF, #3B7DD8);
}

.event-card-title {
  font-size: var(--text-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.event-card-desc {
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

/* ===== Onboarding (placeholder) ===== */
.onboarding-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
}

.onboarding-row:not(:last-child) {
  border-bottom: 1px solid var(--border-subtle);
}

.onboarding-progress-badge {
  margin-left: auto;
  font-size: var(--text-xs);
  color: var(--text-muted);
  background: var(--bg-surface-hover);
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-full);
  white-space: nowrap;
}

/* ===== Chat Widget (shared: dashboard card + FAB panel) ===== */
.chat-card {
  display: flex;
  flex-direction: column;
  min-height: 340px;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-4);
  flex-direction: column;
  gap: var(--space-3);
  display: none; /* chat-widget.js flips this to flex on the first sent message */
}

.chat-message {
  display: flex;
  gap: var(--space-2);
  max-width: 90%;
}

.chat-message.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}

.chat-message.assistant {
  align-self: flex-start;
}

.message-avatar {
  width: 24px;
  height: 24px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xs);
  font-weight: var(--font-weight-semibold);
}

.message-avatar.assistant { background: var(--accent-light); color: var(--accent); }
.message-avatar.user { background: var(--color-neutral-200); color: var(--text-primary); }

.message-content {
  background: var(--bg-surface-hover);
  border-radius: var(--radius-lg);
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
  line-height: var(--leading-normal);
  white-space: pre-wrap;
}

.message-content.user {
  background: var(--accent-light);
}

/* Empty / welcome state */
.ai-welcome {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--space-6);
  gap: var(--space-4);
}

.ai-orb {
  width: 72px;
  height: 72px;
  border-radius: var(--radius-full);
  background: linear-gradient(135deg, #DCEFFF, #A5CCFF, #7FB6FF);
  box-shadow: 0 0 30px oklch(from #7FB6FF l c h / 0.35);
}

.ai-welcome-title {
  font-family: var(--font-display);
  font-size: var(--text-xl);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
}

.ai-quick-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--space-2);
}

.quick-action-btn {
  padding: var(--space-2) var(--space-4);
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-full);
  color: var(--text-secondary);
  font: inherit;
  font-size: var(--text-sm);
  cursor: pointer;
}

.quick-action-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-light);
}

.chat-input-area {
  padding: var(--space-3) var(--space-4);
  border-top: 1px solid var(--border-subtle);
}

.chat-input-wrapper {
  display: flex;
  gap: var(--space-2);
}

.chat-input {
  flex: 1;
  resize: none;
  min-height: 40px;
  max-height: 120px;
  padding: var(--space-2) var(--space-4);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-full);
  background: var(--bg-surface);
  color: var(--text-primary);
  font: inherit;
  font-size: var(--text-sm);
}

.chat-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: var(--focus-ring);
}

.chat-send-btn {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-full);
  background: var(--accent);
  color: var(--accent-foreground);
  border: none;
  cursor: pointer;
  flex-shrink: 0;
}

.chat-send-btn:hover { background: var(--accent-hover); }
.chat-send-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.chat-token-usage {
  font-size: var(--text-xs);
  color: var(--text-muted);
  padding-top: var(--space-2);
}

/* ===== Calendar FAB (floating chat entry point) ===== */
.fab-chat-button {
  position: fixed;
  bottom: var(--space-6);
  right: var(--space-6);
  width: 56px;
  height: 56px;
  border-radius: var(--radius-full);
  background: var(--accent);
  color: var(--accent-foreground);
  border: none;
  box-shadow: var(--shadow-lg);
  cursor: pointer;
  font-size: var(--text-xl);
  z-index: var(--z-popover);
}

.fab-chat-button:hover { background: var(--accent-hover); }

.fab-chat-panel {
  position: fixed;
  bottom: calc(var(--space-6) + 68px);
  right: var(--space-6);
  width: 320px;
  height: 420px;
  background: var(--bg-surface);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-elevated);
  z-index: var(--z-popover);
  display: none;
  flex-direction: column;
}

.fab-chat-panel.open {
  display: flex;
}
```

- [ ] **Step 2: Verify brace balance**

Run:
```bash
node -e "
const fs=require('fs');
const s=fs.readFileSync('static/css/dashboard.css','utf8');
const open=(s.match(/\{/g)||[]).length;
const close=(s.match(/\}/g)||[]).length;
console.log(open, close, open===close ? 'OK' : 'MISMATCH');
"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add static/css/dashboard.css
git commit -m "Add dashboard shell, card, and chat-widget CSS"
```

---

### Task 3: Rewrite `base.html` app shell + minimal dashboard route

`base.html` links to `url_for('dashboard.dashboard_page')`, so the
`dashboard_bp` blueprint must exist before this task's commit or every page
(including `/calendar`) breaks with a Jinja `BuildError`. This task creates
the blueprint with a bare placeholder template; Task 5 fills in the real
content on top of it without touching routing again.

**Files:**
- Modify: `templates/base.html`
- Create: `pages/dashboard/__init__.py`
- Create: `pages/dashboard/routes.py`
- Create: `templates/dashboard.html` (placeholder — replaced in Task 5)
- Modify: `app.py`
- Test: `tests/test_dashboard.py`

**Interfaces:**
- Consumes: `.app-layout`/`.top-bar`/`.sidebar`/`.nav-item`/`.content-area` classes (Task 2).
- Produces: `dashboard_bp` registered at `/`, view name `dashboard.dashboard_page` (used by `base.html`'s own logo/nav link, and by Task 5 which overwrites `templates/dashboard.html` in place); `{% block content %}` and `{% block scripts %}` blocks that `dashboard.html`/`calendar.html` extend; `active_page` Jinja variable for nav highlighting.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dashboard.py
def test_dashboard_page_renders(client):
    response = client.get("/")
    assert response.status_code == 200
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest tests/test_dashboard.py -v`
Expected: FAIL (404, route `/` doesn't exist yet)

- [ ] **Step 3: Create `pages/dashboard/__init__.py`**

```python
```

(empty file, matches `pages/calendar/__init__.py`)

- [ ] **Step 4: Create `pages/dashboard/routes.py`**

```python
from flask import Blueprint, render_template

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def dashboard_page():
    return render_template("dashboard.html")
```

- [ ] **Step 5: Register the blueprint in `app.py`**

Modify `app.py` — add after the existing `calendar_bp` try/except block (around line 19):

```python
    try:
        from pages.dashboard.routes import dashboard_bp
        app.register_blueprint(dashboard_bp)
    except ImportError:
        pass
```

- [ ] **Step 6: Create a placeholder `templates/dashboard.html`**

```html
{% extends "base.html" %}
{% block title %}Dashboard{% endblock %}
{% set active_page = "dashboard" %}
{% block content %}
  <p>Dashboard</p>
{% endblock %}
```

(Task 5 replaces this file's content block with the real cards — routing
and the `dashboard.dashboard_page` endpoint are already correct after this
task, so nothing else needs to change.)

- [ ] **Step 7: Write `templates/base.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}AI Assistant{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/tokens.css') }}">
  <link rel="stylesheet" href="{{ url_for('static', filename='css/depth.css') }}">
  <link rel="stylesheet" href="{{ url_for('static', filename='css/dashboard.css') }}">
  {% block extra_css %}{% endblock %}
</head>
<body data-active-page="{{ active_page }}">
  <div class="app-layout">
    <header class="top-bar">
      <div class="top-bar-left">
        <a href="{{ url_for('dashboard.dashboard_page') }}" class="logo">
          <span class="logo-mark"></span>
          <span class="logo-text">AI Assistant</span>
        </a>
      </div>
      <div class="global-search">
        <input class="search-input" type="text" placeholder="Search..." disabled>
      </div>
      <div class="top-bar-right">
        <span class="user-avatar-placeholder">U</span>
      </div>
    </header>
    <nav class="sidebar">
      <a href="{{ url_for('dashboard.dashboard_page') }}"
         class="nav-item {{ 'active' if active_page == 'dashboard' else '' }}">Dashboard</a>
      <a href="{{ url_for('calendar.calendar_page') }}"
         class="nav-item {{ 'active' if active_page == 'calendar' else '' }}">Calendar</a>
    </nav>
    <main class="content-area">
      {% block content %}{% endblock %}
    </main>
  </div>
  <script src="{{ url_for('static', filename='js/chat-widget.js') }}"></script>
  {% block scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 8: Run the test to confirm it passes**

Run: `pytest tests/test_dashboard.py -v`
Expected: PASS

- [ ] **Step 9: Run the full suite to check nothing broke**

Run: `pytest -v`
Expected: all tests pass (existing `test_app.py`/`test_calendar_routes.py` still hit `/calendar`, which now extends the rewritten `base.html` — this is the check that `url_for('dashboard.dashboard_page')` resolves)

- [ ] **Step 10: Commit**

```bash
git add templates/base.html pages/dashboard app.py templates/dashboard.html tests/test_dashboard.py
git commit -m "Rewrite base.html as topbar/sidebar/content app shell, add minimal dashboard route"
```

---

### Task 4: `chat-widget.js` reusable factory

**Files:**
- Create: `static/js/chat-widget.js`
- Delete: `static/js/chat.js`

**Interfaces:**
- Produces: `window.createChatWidget(container, options)` where `container` is a DOM element containing (at minimum) a `form[data-chat-form]`, `textarea[data-chat-input]`, `div[data-chat-messages]`, and optionally `div[data-chat-tokens]` and an `.ai-welcome` block. On first send, the widget always sets `messages.style.display = "flex"` and hides `.ai-welcome` if present (found via `container.querySelector`). `options.compact` (boolean, default `false`) is only used for callers to signal "no welcome block exists" — the FAB panel simply omits `.ai-welcome` markup, so `querySelector` returns `null` and that line is a no-op.
- Consumed by: `static/js/dashboard.js` (Task 5) and `static/js/calendar.js` (Task 6).

- [ ] **Step 1: Delete the old `chat.js`**

```bash
rm static/js/chat.js
```

- [ ] **Step 2: Write `static/js/chat-widget.js`**

```javascript
function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}

function createChatWidget(container, options = {}) {
  const form = container.querySelector("[data-chat-form]");
  const input = container.querySelector("[data-chat-input]");
  const messages = container.querySelector("[data-chat-messages]");
  const tokenEl = container.querySelector("[data-chat-tokens]");

  function appendMessage(role, text) {
    const row = document.createElement("div");
    row.className = "chat-message " + role;

    const avatar = document.createElement("div");
    avatar.className = "message-avatar " + role;
    avatar.textContent = role === "user" ? "U" : "AI";

    const bubble = document.createElement("div");
    bubble.className = "message-content " + role;
    bubble.innerHTML = escapeHtml(text);

    row.appendChild(avatar);
    row.appendChild(bubble);
    messages.appendChild(row);
    messages.scrollTop = messages.scrollHeight;
  }

  let activated = false;
  function activate() {
    if (activated) return;
    activated = true;
    messages.style.display = "flex";
    const welcome = container.querySelector(".ai-welcome");
    if (welcome) welcome.style.display = "none";
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const text = input.value.trim();
    if (!text) return;

    activate();
    appendMessage("user", text);
    input.value = "";
    input.style.height = "auto";

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const data = await response.json();
      appendMessage("assistant", data.reply);
      if (tokenEl && typeof data.total_tokens === "number") {
        tokenEl.textContent =
          `Tokens: ${data.input_tokens} in + ${data.output_tokens} out = ${data.total_tokens} total`;
      }
    } catch (err) {
      appendMessage("assistant", "Error: " + err.message);
    }
  }

  form.addEventListener("submit", handleSubmit);
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = input.scrollHeight + "px";
  });

  return { appendMessage, activate };
}
```

- [ ] **Step 3: Verify syntax**

Run:
```bash
node --check static/js/chat-widget.js
```

Expected: no output (exit code 0).

- [ ] **Step 4: Commit**

```bash
git add static/js/chat-widget.js
git rm static/js/chat.js
git commit -m "Replace global chat.js with reusable createChatWidget factory"
```

---

### Task 5: Dashboard page content (cards + chat widget)

Task 3 already registered `dashboard_bp` at `/` with a placeholder
template. This task replaces that placeholder with the real cards and
wires up the chat widget — no routing changes needed.

**Files:**
- Modify: `templates/dashboard.html` (replace placeholder content)
- Create: `static/js/dashboard.js`
- Modify: `tests/test_dashboard.py` (strengthen the placeholder test)

**Interfaces:**
- Consumes: `createChatWidget` (Task 4), `.card`/`.employee-cell`/`.leave-block`/`.event-card`/`.onboarding-row`/`.chat-card`/`.ai-welcome`/`.quick-action-btn` CSS (Task 2), `dashboard.dashboard_page` route (Task 3).
- Produces: nothing consumed by later tasks (leaf page).

- [ ] **Step 1: Strengthen the failing test**

Replace the body of `tests/test_dashboard.py` with:

```python
def test_dashboard_page_renders_cards_and_chat(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.data.decode()
    assert "Planned Absences" in body
    assert "Future Events" in body
    assert "Onboarding" in body
    assert 'id="dash-chat"' in body
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest tests/test_dashboard.py -v`
Expected: FAIL (placeholder template only has `<p>Dashboard</p>`, none of the asserted strings are present)

- [ ] **Step 3: Replace `templates/dashboard.html`**

```html
{% extends "base.html" %}
{% block title %}Dashboard{% endblock %}
{% set active_page = "dashboard" %}
{% block content %}
  <section class="card">
    <div class="card-header">
      <span class="card-title">Planned Absences</span>
    </div>
    <div>
      <div class="employee-cell">
        <span class="employee-avatar">EP</span>
        <div class="employee-info">
          <div class="employee-name">Ethan Parker</div>
          <div class="employee-role">Software Engineer</div>
        </div>
        <span class="leave-block vacation">Vacation</span>
      </div>
      <div class="employee-cell">
        <span class="employee-avatar">LC</span>
        <div class="employee-info">
          <div class="employee-name">Liam Carter</div>
          <div class="employee-role">UI/UX Designer</div>
        </div>
        <span class="leave-block paid-leave">Paid Leave</span>
      </div>
      <div class="employee-cell">
        <span class="employee-avatar">NM</span>
        <div class="employee-info">
          <div class="employee-name">Noah Mitchell</div>
          <div class="employee-role">Backend Developer</div>
        </div>
        <span class="leave-block sick-leave">Sick Leave</span>
      </div>
    </div>
  </section>

  <div class="dashboard-cards-row">
    <section class="card">
      <div class="card-header">
        <span class="card-title">Future Events</span>
      </div>
      <div>
        <div class="event-card">
          <span class="event-card-icon"></span>
          <div>
            <div class="event-card-title">Tech Innovations Summit</div>
            <div class="event-card-desc">Dec 5, 14:00 - 15:00</div>
          </div>
        </div>
        <div class="event-card">
          <span class="event-card-icon"></span>
          <div>
            <div class="event-card-title">Software Dev Meetup</div>
            <div class="event-card-desc">Dec 5, 14:00 - 15:00</div>
          </div>
        </div>
      </div>
    </section>

    <section class="card">
      <div class="card-header">
        <span class="card-title">Onboarding</span>
      </div>
      <div>
        <div class="onboarding-row">
          <span class="employee-avatar">SA</span>
          <div class="employee-info">
            <div class="employee-name">Sophia Adams</div>
            <div class="employee-role">UI/UX Designer</div>
          </div>
          <span class="onboarding-progress-badge">5/10 tasks</span>
        </div>
        <div class="onboarding-row">
          <span class="employee-avatar">LM</span>
          <div class="employee-info">
            <div class="employee-name">Lucas Morgan</div>
            <div class="employee-role">Mobile Developer</div>
          </div>
          <span class="onboarding-progress-badge">5/10 tasks</span>
        </div>
      </div>
    </section>

    <section class="card chat-card" id="dash-chat">
      <div class="card-header">
        <span class="card-title">Assistant</span>
      </div>
      <div class="ai-welcome">
        <div class="ai-orb"></div>
        <div class="ai-welcome-title">What can I help with today?</div>
        <div class="ai-quick-actions">
          <button type="button" class="quick-action-btn" data-quick-prompt="What's on my calendar today?">Check calendar</button>
          <button type="button" class="quick-action-btn" data-quick-prompt="Add a new event">Create event</button>
        </div>
      </div>
      <div class="chat-messages" data-chat-messages></div>
      <div class="chat-input-area">
        <form data-chat-form class="chat-input-wrapper">
          <textarea data-chat-input class="chat-input" placeholder="Ask me anything"></textarea>
          <button type="submit" class="chat-send-btn">&#8594;</button>
        </form>
        <div class="chat-token-usage" data-chat-tokens></div>
      </div>
    </section>
  </div>
{% endblock %}
{% block scripts %}
  <script src="{{ url_for('static', filename='js/dashboard.js') }}"></script>
{% endblock %}
```

- [ ] **Step 4: Write `static/js/dashboard.js`**

```javascript
document.addEventListener("DOMContentLoaded", () => {
  const container = document.getElementById("dash-chat");
  if (!container) return;

  const widget = createChatWidget(container, { compact: false });

  container.querySelectorAll("[data-quick-prompt]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const input = container.querySelector("[data-chat-input]");
      input.value = btn.dataset.quickPrompt;
      container.querySelector("[data-chat-form]").requestSubmit();
    });
  });
});
```

- [ ] **Step 5: Verify syntax**

Run:
```bash
node --check static/js/dashboard.js
```
Expected: no output.

- [ ] **Step 6: Run the test to confirm it passes**

Run: `pytest tests/test_dashboard.py -v`
Expected: PASS

- [ ] **Step 7: Run the full suite to check nothing broke**

Run: `pytest -v`
Expected: all tests pass (existing `test_app.py`/`test_calendar_routes.py` still hit `/calendar`, unaffected by the dashboard content change)

- [ ] **Step 8: Commit**

```bash
git add templates/dashboard.html static/js/dashboard.js tests/test_dashboard.py
git commit -m "Add dashboard cards and chat widget content"
```

---

### Task 6: Restyle calendar page + fix events endpoint + FAB chat

**Files:**
- Modify: `templates/calendar.html`
- Rewrite: `static/js/calendar.js`
- Rewrite: `static/css/style.css`
- Modify: `tests/test_calendar_routes.py`

**Interfaces:**
- Consumes: `createChatWidget` and the global `escapeHtml()` (both defined in `chat-widget.js`, Task 4, loaded in `base.html` before any `{% block scripts %}` content — so `calendar.js` can call `escapeHtml()` without redefining it), `.card`/`.fab-chat-button`/`.fab-chat-panel`/`.chat-card` CSS (Task 2), `/calendar/api/events?start=...&end=...` (existing route, requires both params per Global Constraints).
- Produces: nothing consumed by later tasks (leaf page).

- [ ] **Step 1: Write the failing test (FAB markup)**

In `tests/test_calendar_routes.py`, change the existing `test_calendar_page_renders` test from:

```python
def test_calendar_page_renders(client):
    response = client.get("/calendar")
    assert response.status_code == 200
    assert b"calendar" in response.data.lower()
```

to:

```python
def test_calendar_page_renders(client):
    response = client.get("/calendar")
    assert response.status_code == 200
    assert b"calendar" in response.data.lower()
    assert b'id="calendar-fab"' in response.data
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `pytest tests/test_calendar_routes.py::test_calendar_page_renders -v`
Expected: FAIL (`id="calendar-fab"` not in current `calendar.html`)

- [ ] **Step 3: Rewrite `static/css/style.css`**

```css
/* ==========================================================================
   Calendar month-grid styles
   ========================================================================== */

.calendar-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}

.calendar-title {
  font-family: var(--font-display);
  font-size: var(--text-2xl);
  font-weight: var(--font-weight-bold);
  color: var(--text-primary);
}

.cal-grid {
  width: 100%;
  border-collapse: collapse;
}

.cal-grid th {
  padding: var(--space-2);
  font-size: var(--text-xs);
  font-weight: var(--font-weight-semibold);
  color: var(--text-muted);
  text-transform: uppercase;
  border-bottom: 1px solid var(--border-subtle);
}

.cal-grid td {
  vertical-align: top;
  padding: var(--space-2);
  height: 90px;
  border: 1px solid var(--border-subtle);
}

.cal-day .day-num {
  font-size: var(--text-sm);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.day-events {
  list-style: none;
  margin-top: var(--space-1);
}

.day-events li {
  font-size: var(--text-xs);
  background: var(--accent-light);
  color: var(--accent);
  border-radius: var(--radius-sm);
  padding: var(--space-1) var(--space-2);
  margin-top: var(--space-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
```

- [ ] **Step 4: Rewrite `templates/calendar.html`**

```html
{% extends "base.html" %}
{% block title %}Calendar{% endblock %}
{% set active_page = "calendar" %}
{% block extra_css %}
  <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
{% endblock %}
{% block content %}
  <section class="card">
    <div class="card-header">
      <span class="card-title">Calendar</span>
    </div>
    <div class="card-content">
      <div id="calendar"></div>
    </div>
  </section>

  <button type="button" id="calendar-fab" class="fab-chat-button">&#128172;</button>
  <div id="fab-chat-panel" class="fab-chat-panel chat-card">
    <div class="card-header">
      <span class="card-title">Assistant</span>
    </div>
    <div class="chat-messages" data-chat-messages></div>
    <div class="chat-input-area">
      <form data-chat-form class="chat-input-wrapper">
        <textarea data-chat-input class="chat-input" placeholder="Ask me anything"></textarea>
        <button type="submit" class="chat-send-btn">&#8594;</button>
      </form>
      <div class="chat-token-usage" data-chat-tokens></div>
    </div>
  </div>
{% endblock %}
{% block scripts %}
  <script src="{{ url_for('static', filename='js/calendar.js') }}"></script>
{% endblock %}
```

- [ ] **Step 5: Rewrite `static/js/calendar.js`**

```javascript
document.addEventListener("DOMContentLoaded", async () => {
  const cal = document.getElementById("calendar");
  if (cal) {
    await loadCalendar(cal);
  }

  const fab = document.getElementById("calendar-fab");
  const panel = document.getElementById("fab-chat-panel");
  if (fab && panel) {
    let widget = null;
    fab.addEventListener("click", () => {
      panel.classList.toggle("open");
      if (panel.classList.contains("open") && !widget) {
        widget = createChatWidget(panel, { compact: true });
      }
    });
  }
});

async function loadCalendar(cal) {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const start = new Date(year, month, 1).toISOString();
  const end = new Date(year, month + 1, 0, 23, 59, 59).toISOString();

  try {
    const res = await fetch(
      `/calendar/api/events?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`
    );
    const events = await res.json();
    renderCalendar(cal, events, year, month);
  } catch (e) {
    cal.textContent = "Error loading events: " + e.message;
  }
}

function renderCalendar(cal, events, year, month) {
  const now = new Date();
  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const monthName = now.toLocaleString("default", { month: "long" });

  let html = `<div class="calendar-header-row"><span class="calendar-title">${monthName} ${year}</span></div>`;
  html += '<table class="cal-grid"><thead><tr>';
  ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].forEach((d) => {
    html += `<th>${d}</th>`;
  });
  html += "</tr></thead><tbody><tr>";

  let day = 1;
  for (let i = 0; i < 6; i++) {
    for (let j = 0; j < 7; j++) {
      if (i === 0 && j < firstDay) {
        html += "<td></td>";
      } else if (day > daysInMonth) {
        html += "<td></td>";
      } else {
        const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
        const dayEvents = events.filter((e) => e.start.startsWith(dateStr));
        html += `<td class="cal-day"><span class="day-num">${day}</span>`;
        if (dayEvents.length) {
          html += '<ul class="day-events">';
          dayEvents.forEach((e) => {
            html += `<li>${escapeHtml(e.title)}</li>`;
          });
          html += "</ul>";
        }
        html += "</td>";
        day++;
      }
    }
    if (day > daysInMonth) break;
    html += "</tr><tr>";
  }
  html += "</tr></tbody></table>";
  cal.innerHTML = html;
}
```

- [ ] **Step 6: Verify JS syntax**

Run:
```bash
node --check static/js/calendar.js
```
Expected: no output.

- [ ] **Step 7: Run the calendar test to confirm it passes**

Run: `pytest tests/test_calendar_routes.py -v`
Expected: PASS (all 4 tests, including the new FAB assertion)

- [ ] **Step 8: Run the full suite**

Run: `pytest -v`
Expected: all tests pass

- [ ] **Step 9: Commit**

```bash
git add templates/calendar.html static/js/calendar.js static/css/style.css tests/test_calendar_routes.py
git commit -m "Restyle calendar page, fix events endpoint call, add FAB chat"
```

---

### Task 7: Manual verification

**Files:** none (verification only)

- [ ] **Step 1: Run the dev server**

Run: `python app.py`
Expected: server starts on `http://127.0.0.1:5000` without error

- [ ] **Step 2: Load `/` in a browser**

Confirm: topbar + sidebar render, Planned Absences / Future Events / Onboarding cards show placeholder rows, Assistant card shows the welcome orb + quick-action chips.

- [ ] **Step 3: Send a chat message from the dashboard card**

Type a message and submit. Confirm: welcome view is replaced by the message list, a user bubble and an assistant reply bubble appear, token usage line updates.

- [ ] **Step 4: Load `/calendar` in a browser**

Confirm: month grid renders with the current month's events (verifies the `/calendar/api/events` query-param fix), no persistent chat sidebar is present, a floating chat button sits bottom-right.

- [ ] **Step 5: Click the FAB and send a message**

Confirm: panel opens above the button, message send/receive works the same as the dashboard card.

- [ ] **Step 6: Stop the dev server** (Ctrl+C)

No commit for this task — verification only.
