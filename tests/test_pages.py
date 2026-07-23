import pytest

PAGES = {
    "/": b"Today's events",
    "/calendar": b"cal-grid",
    "/todos": b"Master List",
    "/settings": b"Settings",
}


@pytest.mark.parametrize("path,marker", PAGES.items())
def test_page_ok(client, path, marker):
    res = client.get(path)
    assert res.status_code == 200
    assert marker in res.data


@pytest.mark.parametrize("path", PAGES)
def test_no_external_cdn(client, path):
    """No-CDN guarantee: fonts/icons/styles are self-hosted."""
    html = client.get(path).data
    for banned in (b"cdn.tailwindcss.com", b"fonts.googleapis.com", b"fonts.gstatic.com"):
        assert banned not in html


def test_icons_are_inline_svg(client):
    """Lucide icons render as inline SVG, never emoji or icon fonts."""
    html = client.get("/").data
    assert b"<svg" in html and b"material-symbols" not in html
