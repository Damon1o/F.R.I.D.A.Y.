### Task 07: Todos API + To-Do page

Build the Todos JSON API blueprint and the `/todos` page (template + CSS + JS) for Kiko.
The API mirrors the events API's structure and error mapping exactly; the page is brand
new (no git history) and is designed from scratch on top of the recovered glassmorphism
design tokens.

---

#### Context the implementer must honor (recap of global constraints)

- **Stack:** Python 3, Flask app-factory pattern. Server-rendered Jinja + vanilla JS
  `fetch`. **No build step, no frontend framework.**
- **Persistence:** stdlib `sqlite3` only (all DB work already lives behind the Task 06
  `pages/todos/models.py` functions — this task never touches SQL directly).
- **Single user, localhost.** No auth, no sessions.
- **Datetimes:** stored as ISO-8601 UTC text; the frontend renders local time and converts
  local `<input type="datetime-local">` values to UTC ISO before sending.
- **Icons:** self-hosted, pinned Lucide **SVG only**. **No emojis / no Unicode glyphs
  anywhere in the UI.** This task inlines the exact Lucide 24×24 path data (shown in full
  below) so the page never depends on an emoji or an external icon runtime.
- **Design:** reuse the glassmorphism system already recovered by earlier tasks —
  `static/css/tokens.css` (color/space/type/radius/motion CSS variables) and
  `static/css/depth.css` (`.glass-card`, neumorphism helpers). This task's `todos.css`
  only consumes those `var(--…)` tokens; it never hardcodes colors.
- **TDD:** write the failing test first, run it and watch it fail, write the minimal code,
  run it and watch it pass, then commit. Small, frequent commits.
- **DRY / YAGNI:** no priority, tags, recurring, subtasks, or reminders in Phase 1.

**Prerequisites already in place from earlier tasks (do not recreate):**

- Task 01 — `app.py` (`create_app(test_config)`), `config.py`, `core/errors.py`
  (`class ValidationError(Exception)`).
- Task 02 — `core/db.py` and `tests/conftest.py` exposing a pytest `client` fixture backed
  by an in-memory / isolated SQLite database with `schema.sql` applied.
- Task 03 — `templates/base.html` exposing Jinja blocks **`title`**, **`content`**,
  **`page_scripts`**, plus the sidebar nav (`/`, `/calendar`, `/todos`) and theme toggle.
  base.html links `tokens.css` + `depth.css` globally. It exposes **no** per-page CSS
  block, so this task links `todos.css` from inside the `content` block (a `<link>` in
  `<body>` is valid HTML5 and works reliably).
- Task 06 — `pages/todos/models.py` and `pages/todos/__init__.py` (the `pages/todos`
  package already exists).

---

**Files:**

- **Create:**
  - `pages/todos/routes.py` — `todos_bp` blueprint (page route + JSON CRUD API).
  - `templates/todos.html` — the To-Do page, extends `base.html`.
  - `static/css/todos.css` — page styles (glassmorphism tokens only).
  - `static/js/todos.js` — vanilla-JS interactions (load / add / complete / edit / delete).
- **Modify:**
  - `app.py` — register `todos_bp` inside `create_app`.
- **Test:**
  - `tests/test_todos_api.py` — API + page smoke tests.

**Interfaces:**

- **Consumes** (exact signatures — do not deviate):
  - `pages/todos/models.py` (Task 06):
    - `create_todo(data: dict) -> dict`  — keys: `title` (req), `due_at?`, `notes?`
    - `get_todo(todo_id: int) -> dict | None`
    - `list_todos(done: bool | None = None) -> list[dict]`
    - `update_todo(todo_id: int, data: dict) -> dict | None`  — toggling `done` sets/clears `completed_at`
    - `delete_todo(todo_id: int) -> bool`
    - Returned dicts include `id`, `title`, `due_at`, `done` (bool), `notes`,
      `created_at`, `completed_at`.
  - `core/errors.py` (Task 01): `class ValidationError(Exception)` — raised by the model on
    bad input; routes map it to HTTP 400.
  - `templates/base.html` (Task 03): blocks `title`, `content`, `page_scripts`.
- **Produces** (must match the global contract exactly):
  - `pages/todos/routes.py`: blueprint name `'todos'`, variable `todos_bp`.
  - `GET  /todos`
  - `GET  /api/todos?done=`
  - `POST /api/todos`
  - `PATCH  /api/todos/<int:todo_id>`
  - `DELETE /api/todos/<int:todo_id>`

---

#### Steps

- [ ] **Step 1: Write the failing Todos API tests.**
  Create `tests/test_todos_api.py`. These cover only the JSON API for now (the page smoke
  test is added later, after the API cycle is green, to keep every commit green). They rely
  on the shared `client` fixture from `tests/conftest.py` (Task 02).

  ```python
  # tests/test_todos_api.py
  """API tests for the Todos blueprint (Task 07)."""


  def test_post_valid_todo_returns_201(client):
      resp = client.post("/api/todos", json={"title": "Buy milk"})
      assert resp.status_code == 201
      body = resp.get_json()
      assert body["id"] > 0
      assert body["title"] == "Buy milk"
      assert body["done"] is False
      assert body["completed_at"] is None


  def test_post_empty_title_returns_400(client):
      resp = client.post("/api/todos", json={"title": "   "})
      assert resp.status_code == 400
      assert "error" in resp.get_json()


  def test_post_missing_body_returns_400(client):
      resp = client.post("/api/todos", json={})
      assert resp.status_code == 400
      assert "error" in resp.get_json()


  def test_get_todos_done_filter(client):
      client.post("/api/todos", json={"title": "open task"})
      done = client.post("/api/todos", json={"title": "finished task"}).get_json()
      client.patch(f"/api/todos/{done['id']}", json={"done": True})

      done_only = client.get("/api/todos?done=1")
      assert done_only.status_code == 200
      assert [t["title"] for t in done_only.get_json()] == ["finished task"]

      open_only = client.get("/api/todos?done=0")
      assert [t["title"] for t in open_only.get_json()] == ["open task"]

      all_todos = client.get("/api/todos")
      assert len(all_todos.get_json()) == 2


  def test_patch_toggle_done_sets_and_clears_completed_at(client):
      created = client.post("/api/todos", json={"title": "task"}).get_json()
      assert created["completed_at"] is None

      toggled = client.patch(f"/api/todos/{created['id']}", json={"done": True})
      assert toggled.status_code == 200
      done_body = toggled.get_json()
      assert done_body["done"] is True
      assert done_body["completed_at"] is not None

      cleared = client.patch(f"/api/todos/{created['id']}", json={"done": False}).get_json()
      assert cleared["done"] is False
      assert cleared["completed_at"] is None


  def test_patch_missing_todo_returns_404(client):
      resp = client.patch("/api/todos/999999", json={"done": True})
      assert resp.status_code == 404
      assert "error" in resp.get_json()


  def test_delete_todo_returns_204(client):
      created = client.post("/api/todos", json={"title": "temp"}).get_json()
      resp = client.delete(f"/api/todos/{created['id']}")
      assert resp.status_code == 204
      assert resp.data == b""
      assert client.get("/api/todos").get_json() == []


  def test_delete_missing_todo_returns_404(client):
      resp = client.delete("/api/todos/999999")
      assert resp.status_code == 404
  ```

- [ ] **Step 2: Run the API tests — expect FAIL.**
  ```bash
  python -m pytest tests/test_todos_api.py -v
  ```
  Expected: every test fails because no `/api/todos` routes are registered yet — Flask
  returns `404` for the unknown routes, e.g.
  `test_post_valid_todo_returns_201` fails with `assert 404 == 201`.

- [ ] **Step 3: Implement `pages/todos/routes.py`.**
  Create the blueprint with the page route and the four JSON endpoints. The error mapping
  is identical to the events API: catch `ValidationError` → `400 {"error": …}`; a missing
  resource → `404 {"error": …}`. The `done` query param is `"1"`/`"0"`; absent means "all".

  ```python
  # pages/todos/routes.py
  """Todos blueprint: /todos page + /api/todos JSON CRUD (Task 07)."""
  from flask import Blueprint, jsonify, render_template, request

  from core.errors import ValidationError
  from pages.todos import models

  todos_bp = Blueprint("todos", __name__)


  @todos_bp.get("/todos")
  def todos_page():
      return render_template("todos.html", active_page="todos")


  @todos_bp.get("/api/todos")
  def list_todos_api():
      done_arg = request.args.get("done")
      done = None if done_arg is None else (done_arg == "1")
      return jsonify(models.list_todos(done=done))


  @todos_bp.post("/api/todos")
  def create_todo_api():
      data = request.get_json(silent=True) or {}
      try:
          todo = models.create_todo(data)
      except ValidationError as exc:
          return jsonify({"error": str(exc)}), 400
      return jsonify(todo), 201


  @todos_bp.patch("/api/todos/<int:todo_id>")
  def update_todo_api(todo_id):
      data = request.get_json(silent=True) or {}
      try:
          todo = models.update_todo(todo_id, data)
      except ValidationError as exc:
          return jsonify({"error": str(exc)}), 400
      if todo is None:
          return jsonify({"error": "Todo not found"}), 404
      return jsonify(todo)


  @todos_bp.delete("/api/todos/<int:todo_id>")
  def delete_todo_api(todo_id):
      if not models.delete_todo(todo_id):
          return jsonify({"error": "Todo not found"}), 404
      return "", 204
  ```

- [ ] **Step 4: Register `todos_bp` in `app.py`.**
  Open `app.py` and, inside `create_app`, next to the existing blueprint registrations
  (`calendar_bp`, `dashboard_bp`, etc.), add the import and registration. Keep the import
  inside the factory, consistent with the other blueprints:

  ```python
      # inside create_app(...), with the other register_blueprint(...) calls:
      from pages.todos.routes import todos_bp
      app.register_blueprint(todos_bp)
  ```

- [ ] **Step 5: Run the API tests — expect PASS.**
  ```bash
  python -m pytest tests/test_todos_api.py -v
  ```
  Expected: all 8 API tests pass (`8 passed`). The `/todos` page route now exists too but
  is not yet exercised by a test (its template arrives in Step 8).

- [ ] **Step 6: Commit the API layer.**
  ```bash
  git add pages/todos/routes.py app.py tests/test_todos_api.py
  git commit -m "$(cat <<'EOF'
  feat(todos): add todos_bp JSON API with tests

  Add /api/todos CRUD (GET list with done filter, POST, PATCH, DELETE) and
  the /todos page route; map ValidationError to 400 and missing ids to 404,
  matching the events API. Register todos_bp in the app factory.

  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  EOF
  )"
  ```

- [ ] **Step 7: Add the failing page smoke test.**
  Append this test to `tests/test_todos_api.py`. It pins the markers the template must
  emit — the page heading, the add-task form, and the `todos.css` / `todos.js` references —
  so the template + its asset wiring stay verified.

  ```python
  def test_todos_page_smoke(client):
      resp = client.get("/todos")
      assert resp.status_code == 200
      html = resp.data.lower()
      assert b"to-do" in html                 # page heading / title
      assert b'id="todo-form"' in html        # add-task form present
      assert b"css/todos.css" in html         # page stylesheet linked
      assert b"js/todos.js" in html           # page script linked
  ```

  Run it — expect FAIL:
  ```bash
  python -m pytest tests/test_todos_api.py::test_todos_page_smoke -v
  ```
  Expected: the route calls `render_template("todos.html", …)` but the template does not
  exist yet, so pytest reports an error:
  `jinja2.exceptions.TemplateNotFound: todos.html`.

- [ ] **Step 8: Design the page, then create `templates/todos.html`.**
  **Before writing markup, invoke the frontend-design skill** for layout and visual polish
  guidance:
  ```
  Skill tool -> skill: "frontend-design"
  ```
  Design brief to hold to while applying the skill: a single, calm, centered task list on
  the glassmorphism canvas; a prominent glass "add task" bar at the top (title input +
  optional due-date + add button); open tasks first (overdue flagged in the error color),
  a muted "Completed" section below with strikethrough titles. **Reuse the recovered
  `tokens.css` + `depth.css` tokens/classes (e.g. `.glass-card`); use ONLY the inlined
  Lucide SVGs below — never an emoji or Unicode glyph.**

  The `<link>` for `todos.css` goes at the top of the `content` block (base.html exposes no
  CSS block), and the `<script>` goes in the `page_scripts` block. The add button uses the
  inlined Lucide **plus** icon.

  ```html
  {% extends "base.html" %}
  {% block title %}To-Do — Kiko{% endblock %}
  {% block content %}
  <link rel="stylesheet" href="{{ url_for('static', filename='css/todos.css') }}">
  <section class="todos-page">
    <header class="todos-header">
      <h1 class="todos-heading">To-Do</h1>
      <p class="todos-subtitle">Everything on your plate, one clear list.</p>
    </header>

    <form id="todo-form" class="todo-add glass-card" autocomplete="off">
      <input id="todo-title-input" class="todo-add-title" type="text"
             placeholder="Add a task…" aria-label="Task title" required>
      <input id="todo-due-input" class="todo-add-due" type="datetime-local"
             aria-label="Due date (optional)">
      <button type="submit" class="todo-add-btn" aria-label="Add task">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24"
             fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"
             stroke-linejoin="round"><path d="M5 12h14"/><path d="M12 5v14"/></svg>
        <span>Add</span>
      </button>
    </form>

    <ul id="todo-list" class="todo-list glass-card" aria-label="Open tasks"></ul>

    <section id="todo-completed-section" class="todo-completed-section" hidden>
      <h2 class="todo-completed-heading">Completed</h2>
      <ul id="todo-completed" class="todo-list todo-list-done glass-card"
          aria-label="Completed tasks"></ul>
    </section>
  </section>
  {% endblock %}
  {% block page_scripts %}
  <script src="{{ url_for('static', filename='js/todos.js') }}"></script>
  {% endblock %}
  ```

- [ ] **Step 9: Run the page smoke test — expect PASS.**
  ```bash
  python -m pytest tests/test_todos_api.py::test_todos_page_smoke -v
  ```
  Expected: `1 passed`. (`todos.css` / `todos.js` return 404 at runtime for now — they are
  created next — but the page HTML is served `200` with the required markers.)

- [ ] **Step 10: Commit the page template.**
  ```bash
  git add templates/todos.html tests/test_todos_api.py
  git commit -m "$(cat <<'EOF'
  feat(todos): add To-Do page template with smoke test

  Add templates/todos.html (extends base.html; blocks title/content/page_scripts)
  with the glass add-task bar, open-task list, and completed section. Lucide plus
  icon inlined as SVG. Smoke test asserts heading, form, and asset links.

  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  EOF
  )"
  ```

- [ ] **Step 11: Create `static/css/todos.css`.**
  Styles consume `tokens.css` / `depth.css` variables only — no hardcoded colors. Overdue
  rows get a left accent bar in `--error`; done rows strike through and mute. Wraps the add
  bar on narrow viewports.

  ```css
  /* static/css/todos.css — To-Do page (Kiko Phase 1).
     Consumes design tokens from tokens.css + depth.css only. */

  .todos-page {
    max-width: 720px;
    margin: 0 auto;
    padding: var(--space-6) var(--space-4) var(--space-12);
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  .todos-header { display: flex; flex-direction: column; gap: var(--space-1); }

  .todos-heading {
    font-family: var(--font-display);
    font-size: var(--text-3xl);
    font-weight: var(--font-weight-bold);
    color: var(--text-primary);
    line-height: var(--leading-tight);
  }

  .todos-subtitle { color: var(--text-secondary); font-size: var(--text-base); }

  /* ----- Add-task bar ----- */
  .todo-add {
    display: flex;
    gap: var(--space-3);
    align-items: center;
    padding: var(--space-3);
    border-radius: var(--radius-lg);
  }

  .todo-add-title {
    flex: 1 1 auto;
    min-width: 0;
    background: transparent;
    border: none;
    outline: none;
    color: var(--text-primary);
    font-family: var(--font-body);
    font-size: var(--text-base);
    padding: var(--space-2);
  }
  .todo-add-title::placeholder { color: var(--text-muted); }

  .todo-add-due {
    flex: 0 0 auto;
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-md);
    color: var(--text-secondary);
    font-family: var(--font-body);
    font-size: var(--text-sm);
    padding: var(--space-2);
  }

  .todo-add-btn {
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    background: var(--accent);
    color: var(--accent-foreground);
    border: none;
    border-radius: var(--radius-md);
    padding: var(--space-2) var(--space-4);
    font-family: var(--font-body);
    font-size: var(--text-sm);
    font-weight: var(--font-weight-semibold);
    cursor: pointer;
    transition: background var(--duration-fast) var(--ease-out-quart),
                transform var(--duration-fast) var(--ease-out-quart);
  }
  .todo-add-btn:hover { background: var(--accent-hover); }
  .todo-add-btn:active { transform: scale(0.97); }

  /* ----- List ----- */
  .todo-list {
    list-style: none;
    margin: 0;
    padding: var(--space-2);
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    border-radius: var(--radius-lg);
  }

  .todo-item {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-3);
    border-radius: var(--radius-md);
    transition: background var(--duration-fast) var(--ease-out-quart);
  }
  .todo-item:hover { background: var(--bg-surface-hover); }

  .todo-checkbox {
    flex: 0 0 auto;
    width: 20px;
    height: 20px;
    accent-color: var(--accent);
    cursor: pointer;
  }

  .todo-main {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .todo-title {
    color: var(--text-primary);
    font-size: var(--text-base);
    cursor: text;
    word-break: break-word;
  }

  .todo-edit-input {
    width: 100%;
    background: var(--bg-surface);
    border: 1px solid var(--accent);
    border-radius: var(--radius-sm);
    color: var(--text-primary);
    font-family: var(--font-body);
    font-size: var(--text-base);
    padding: var(--space-1) var(--space-2);
    outline: none;
  }

  .todo-due {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    color: var(--text-muted);
    font-size: var(--text-xs);
  }
  .todo-due svg { flex: 0 0 auto; }

  .todo-delete {
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    color: var(--text-muted);
    padding: var(--space-2);
    border-radius: var(--radius-md);
    cursor: pointer;
    transition: color var(--duration-fast), background var(--duration-fast);
  }
  .todo-delete:hover { color: var(--error); background: var(--bg-surface-active); }

  /* ----- Done state ----- */
  .todo-item.done .todo-title {
    text-decoration: line-through;
    color: var(--text-muted);
  }

  /* ----- Overdue flag ----- */
  .todo-item.overdue { box-shadow: inset 3px 0 0 var(--error); }
  .todo-item.overdue .todo-due { color: var(--error); }

  /* ----- Completed section ----- */
  .todo-completed-section { display: flex; flex-direction: column; gap: var(--space-2); }
  .todo-completed-heading {
    font-family: var(--font-display);
    font-size: var(--text-sm);
    font-weight: var(--font-weight-semibold);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-muted);
    padding-left: var(--space-2);
  }
  .todo-list-done { opacity: 0.75; }

  /* ----- Empty / message row ----- */
  .todo-empty {
    color: var(--text-muted);
    font-size: var(--text-sm);
    text-align: center;
    padding: var(--space-5);
  }

  /* ----- Responsive ----- */
  @media (max-width: 560px) {
    .todo-add { flex-wrap: wrap; }
    .todo-add-title { flex: 1 1 100%; }
    .todo-add-due { flex: 1 1 auto; }
  }
  ```

- [ ] **Step 12: Create `static/js/todos.js`.**
  Vanilla JS, no framework. Loads all todos, splits open vs. completed, sorts open by due
  date (overdue first), renders rows, and wires add / toggle-complete / inline-edit /
  delete against the API. Lucide trash / clock / alert icons are inlined SVG strings.
  Local `<datetime-local>` values are converted to UTC ISO with `toISOString()`; stored UTC
  is rendered in local time. `escapeHtml` guards the one place `innerHTML` is used.

  ```javascript
  // static/js/todos.js — To-Do page interactions (Kiko Phase 1). No framework.
  (function () {
    "use strict";

    const listEl = document.getElementById("todo-list");
    const completedEl = document.getElementById("todo-completed");
    const completedSection = document.getElementById("todo-completed-section");
    const formEl = document.getElementById("todo-form");
    const titleInput = document.getElementById("todo-title-input");
    const dueInput = document.getElementById("todo-due-input");

    // Self-hosted, pinned Lucide 24x24 SVG path data (no emojis).
    const ICONS = {
      trash:
        '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/></svg>',
      clock:
        '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
      alert:
        '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>',
    };

    function escapeHtml(value) {
      const div = document.createElement("div");
      div.textContent = value == null ? "" : String(value);
      return div.innerHTML;
    }

    async function api(method, url, body) {
      const opts = { method, headers: { "Content-Type": "application/json" } };
      if (body !== undefined) opts.body = JSON.stringify(body);
      const res = await fetch(url, opts);
      if (res.status === 204) return null;
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error((data && data.error) || `Request failed (${res.status})`);
      }
      return data;
    }

    function formatDue(iso) {
      return new Date(iso).toLocaleString([], {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
    }

    function isOverdue(todo) {
      return !todo.done && !!todo.due_at && new Date(todo.due_at) < new Date();
    }

    function todoRow(todo) {
      const li = document.createElement("li");
      li.className =
        "todo-item" + (todo.done ? " done" : "") + (isOverdue(todo) ? " overdue" : "");
      li.dataset.id = todo.id;

      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.className = "todo-checkbox";
      checkbox.checked = !!todo.done;
      checkbox.setAttribute("aria-label", "Mark complete");
      checkbox.addEventListener("change", () => toggleDone(todo, checkbox.checked));

      const main = document.createElement("div");
      main.className = "todo-main";

      const title = document.createElement("span");
      title.className = "todo-title";
      title.textContent = todo.title;
      title.tabIndex = 0;
      title.addEventListener("click", () => startEdit(li, todo));

      main.appendChild(title);

      if (todo.due_at) {
        const due = document.createElement("span");
        due.className = "todo-due";
        due.innerHTML =
          (isOverdue(todo) ? ICONS.alert : ICONS.clock) +
          "<span>" +
          escapeHtml(formatDue(todo.due_at)) +
          "</span>";
        main.appendChild(due);
      }

      const del = document.createElement("button");
      del.type = "button";
      del.className = "todo-delete";
      del.setAttribute("aria-label", "Delete task");
      del.innerHTML = ICONS.trash;
      del.addEventListener("click", () => removeTodo(todo));

      li.appendChild(checkbox);
      li.appendChild(main);
      li.appendChild(del);
      return li;
    }

    function startEdit(li, todo) {
      if (li.querySelector(".todo-edit-input")) return;
      const title = li.querySelector(".todo-title");
      const input = document.createElement("input");
      input.type = "text";
      input.className = "todo-edit-input";
      input.value = todo.title;
      title.replaceWith(input);
      input.focus();
      input.select();

      let settled = false;
      const commit = async (save) => {
        if (settled) return;
        settled = true;
        const value = input.value.trim();
        if (save && value && value !== todo.title) {
          try {
            await api("PATCH", `/api/todos/${todo.id}`, { title: value });
          } catch (e) {
            alert(e.message);
          }
        }
        load();
      };
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") commit(true);
        else if (e.key === "Escape") commit(false);
      });
      input.addEventListener("blur", () => commit(true));
    }

    async function toggleDone(todo, done) {
      try {
        await api("PATCH", `/api/todos/${todo.id}`, { done });
      } catch (e) {
        alert(e.message);
      }
      load();
    }

    async function removeTodo(todo) {
      try {
        await api("DELETE", `/api/todos/${todo.id}`);
      } catch (e) {
        alert(e.message);
      }
      load();
    }

    function render(todos) {
      const open = todos.filter((t) => !t.done);
      const done = todos.filter((t) => t.done);

      open.sort((a, b) => {
        if (!a.due_at && !b.due_at) return b.id - a.id;
        if (!a.due_at) return 1;
        if (!b.due_at) return -1;
        return new Date(a.due_at) - new Date(b.due_at);
      });
      done.sort(
        (a, b) => new Date(b.completed_at || 0) - new Date(a.completed_at || 0)
      );

      listEl.innerHTML = "";
      if (!open.length) {
        const empty = document.createElement("li");
        empty.className = "todo-empty";
        empty.textContent = "No open tasks. Nice work.";
        listEl.appendChild(empty);
      } else {
        open.forEach((t) => listEl.appendChild(todoRow(t)));
      }

      completedEl.innerHTML = "";
      done.forEach((t) => completedEl.appendChild(todoRow(t)));
      completedSection.hidden = done.length === 0;
    }

    async function load() {
      try {
        render(await api("GET", "/api/todos"));
      } catch (e) {
        listEl.innerHTML = "";
        const err = document.createElement("li");
        err.className = "todo-empty";
        err.textContent = "Could not load tasks: " + e.message;
        listEl.appendChild(err);
      }
    }

    formEl.addEventListener("submit", async (e) => {
      e.preventDefault();
      const title = titleInput.value.trim();
      if (!title) return;
      const body = { title };
      if (dueInput.value) body.due_at = new Date(dueInput.value).toISOString();
      try {
        await api("POST", "/api/todos", body);
        titleInput.value = "";
        dueInput.value = "";
        titleInput.focus();
      } catch (err) {
        alert(err.message);
      }
      load();
    });

    load();
  })();
  ```

- [ ] **Step 13: Verify the whole task — automated + manual.**
  Run the full test module (all 9 tests) and confirm green:
  ```bash
  python -m pytest tests/test_todos_api.py -v
  ```
  Expected: `9 passed`.

  Then manually verify the live page (do not commit until this passes):
  ```bash
  flask --app app run --host 127.0.0.1 --port 5000
  ```
  Open `http://127.0.0.1:5000/todos` and confirm:
  1. Add a task (title only) → it appears instantly in the open list.
  2. Add a task with a past due date → it renders in the error color with the alert icon
     (overdue) and sorts to the top of the open list.
  3. Check a task → it strikes through and moves into the "Completed" section.
  4. Click a title → it becomes an inline input; Enter saves, Escape cancels.
  5. Click the trash icon → the task disappears.
  6. Toggle the theme (sidebar toggle) → colors adapt in both light and dark.
  7. Confirm there are **no emojis/Unicode glyphs** anywhere — all icons are Lucide SVG.

- [ ] **Step 14: Commit the frontend.**
  ```bash
  git add static/css/todos.css static/js/todos.js
  git commit -m "$(cat <<'EOF'
  feat(todos): add To-Do page styles and interactions

  Add todos.css (glassmorphism tokens, overdue flag, done strikethrough,
  responsive add bar) and todos.js (load, add with optional UTC due date,
  toggle complete, inline title edit, delete). Lucide SVG icons only.

  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  EOF
  )"
  ```
