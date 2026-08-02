"""Quality-of-life additions: palette, shortcuts, toasts, skeletons, empty states, density.

These are client-side features, and the project has no JS test runner. What is worth
asserting from Python is the contract the server side of them depends on: the assets
exist, the markup is rendered, and — the ones that actually catch bugs — every icon a
JS module names is on disk, every go-to destination resolves to a real route, and the
compact density block does not touch the week grid's pixel-per-minute scale.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "static" / "js"
CSS = ROOT / "static" / "css"
LUCIDE = ROOT / "static" / "vendor" / "lucide"


def _icons_named_in(path: Path) -> set[str]:
    """Every `/static/vendor/lucide/<name>.svg` referenced from a JS file."""
    return set(re.findall(r"/static/vendor/lucide/([\w-]+)\.svg", path.read_text(encoding="utf-8")))


# ---- assets are wired in ----

@pytest.mark.parametrize("name", ["toast.js", "palette.js", "shortcuts.js", "menu.js"])
def test_module_is_loaded_by_base_template(name):
    base = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    assert f"js/{name}" in base


def test_toast_loads_before_the_page_modules_that_call_it():
    # calendar.js/todos.js call window.toast during their own init.
    base = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    assert base.index("js/toast.js") < base.index("{% block scripts %}")


def test_palette_markup_is_present_and_hidden(client):
    html = client.get("/todos").get_data(as_text=True)
    assert 'id="palette"' in html and 'id="palette-input"' in html
    assert re.search(r'class="palette-scrim" id="palette" hidden', html)


# ---- the tests that actually catch something ----

@pytest.mark.parametrize("module", ["toast.js", "palette.js"])
def test_every_named_lucide_icon_exists_on_disk(module):
    """A missing vendor asset is a broken image inside the UI meant to reassure."""
    missing = sorted(n for n in _icons_named_in(JS / module) if not (LUCIDE / f"{n}.svg").exists())
    assert not missing, f"{module} references missing Lucide icons: {missing}"


def test_empty_state_icons_exist_on_disk():
    """Icons named from templates, which the JS scan above cannot see."""
    for name in ("circle-check-big", "file-text", "message-square"):
        assert (LUCIDE / f"{name}.svg").exists()


def test_goto_shortcut_destinations_all_resolve(app):
    """A dead `g x` chord is silent — nothing surfaces the 404 but the user."""
    source = (JS / "shortcuts.js").read_text(encoding="utf-8")
    block = re.search(r"var GO = \{(.*?)\};", source, re.S).group(1)
    paths = re.findall(r"'([^']+)'", block)
    assert paths, "GO table parsed as empty"
    known = {r.rule for r in app.url_map.iter_rules()}
    assert set(paths) <= known


def test_palette_command_urls_all_resolve(app):
    source = (JS / "palette.js").read_text(encoding="utf-8")
    urls = set(re.findall(r"url: '([^']+)'", source))
    known = {r.rule for r in app.url_map.iter_rules()}
    assert urls <= known


def test_compact_density_does_not_rescale_the_week_grid():
    """calendar-week.js positions chips, the now-line, and its initial scroll at
    1px per minute. A density override of the hour height silently misplaces every
    event in the week view."""
    tokens = (CSS / "tokens.css").read_text(encoding="utf-8")
    block = re.search(r":root\[data-density='compact'\]\s*\{(.*?)\}", tokens, re.S).group(1)
    assert "--cal-hour-h" not in block
    assert "--s-4" in block, "compact must override the spacing scale to do anything"


def test_shortcut_table_rows_are_complete():
    source = (JS / "shortcuts.js").read_text(encoding="utf-8")
    rows = re.findall(r"\{ keys: '([^']*)', label: '([^']*)' \}", source)
    assert len(rows) >= 10
    assert all(keys and label for keys, label in rows)


# ---- right-click replaces the add / row buttons ----

def test_menu_loads_before_the_page_modules_that_bind_to_it():
    """todos.js, notes.js, skills.js and calendar-week.js all call ctxMenu during init."""
    base = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    assert base.index("js/menu.js") < base.index("{% block scripts %}")


@pytest.mark.parametrize("template", ["todos.html", "notes.html", "skills.html", "_gpa_card.html"])
def test_no_plus_icon_buttons_remain(template):
    """Adding is a right-click now; a leftover + button is a second, stale path."""
    html = (ROOT / "templates" / template).read_text(encoding="utf-8")
    assert "icon('plus'" not in html


@pytest.mark.parametrize("page,gone", [
    ("/todos", ["data-check", "data-delete"]),
    ("/notes", ["data-delete"]),
])
def test_row_action_buttons_are_gone_from_the_markup(client, page, gone):
    html = client.get(page).get_data(as_text=True)
    for marker in gone:
        assert marker not in html


def test_every_module_that_calls_ctxmenu_is_actually_shipped():
    """Binding a menu on a page whose script never loads is a silently dead feature."""
    for module, template in [
        ("todos.js", "todos.html"),
        ("notes.js", "notes.html"),
        ("skills.js", "skills.html"),
        ("calendar-week.js", "calendar.html"),
    ]:
        assert "ctxMenu" in (JS / module).read_text(encoding="utf-8")
        assert f"js/{module}" in (ROOT / "templates" / template).read_text(encoding="utf-8")


# ---- design-system rules hold for the new CSS ----

@pytest.mark.parametrize("selector", [".toast", ".empty-state", ".skeleton", ".palette"])
def test_new_component_css_exists(selector):
    assert selector + " " in (CSS / "app.css").read_text(encoding="utf-8") or \
           selector + "," in (CSS / "app.css").read_text(encoding="utf-8") or \
           selector + "\n" in (CSS / "app.css").read_text(encoding="utf-8")


def test_skeleton_respects_reduced_motion():
    css = (CSS / "app.css").read_text(encoding="utf-8")
    blocks = re.findall(r"@media \(prefers-reduced-motion: reduce\) \{(.*?)\}\s*\}", css, re.S)
    assert any(".skeleton" in b for b in blocks)


def test_settings_page_renders_density_and_shortcut_host(client):
    html = client.get("/settings").get_data(as_text=True)
    assert 'id="shortcut-list"' in html
    assert 'data-density-set="compact"' in html
    assert 'data-density-set="comfortable"' in html
