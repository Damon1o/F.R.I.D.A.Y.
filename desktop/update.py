"""Update check for the installed Windows build: ask GitHub for the latest release once
at boot, off the request path. No download, no updater service — the toast links to the
release page and the user runs the installer.
"""
import threading

import requests

from config import VERSION

RELEASES = "https://api.github.com/repos/Damon1o/F.R.I.D.A.Y./releases/latest"


def _newer(tag: str) -> bool:
    """Compare dotted versions numerically. Anything unparseable ⇒ not newer."""
    try:
        parts = tuple(int(p) for p in tag.lstrip("v").split("."))
        return parts > tuple(int(p) for p in VERSION.split("."))
    except ValueError:
        return False


def check_async(app) -> None:
    def run():
        try:
            rel = requests.get(RELEASES, timeout=3).json()
        except Exception:
            return  # no network, rate limited, no releases yet — all equally uninteresting
        tag = rel.get("tag_name") or ""
        if _newer(tag):
            app.config["UPDATE"] = {"version": tag, "url": rel.get("html_url")}

    threading.Thread(target=run, daemon=True).start()

    @app.get("/api/update")
    def update_status():
        return app.config.get("UPDATE") or {}
