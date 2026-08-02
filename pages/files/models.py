"""Filesystem browsing and edits for the desktop build, plus the local change log.

The log is a SQLite file next to the app's settings, not a Postgres table: it records what
this machine's copy did to this machine's files, so it has no business in the cloud DB —
and it must still be readable when Neon is unreachable.

Deletes go to the Recycle Bin (SHFileOperation with FOF_ALLOWUNDO), never `os.remove` —
a mis-click in a browser UI should be recoverable.
"""
import ctypes
import os
import sqlite3
import time
from pathlib import Path

from flask import current_app

TEXT_CAP = 512 * 1024   # preview/edit ceiling; bigger files open read-only-truncated
SEARCH_CAP = 200        # results
SEARCH_SECONDS = 5.0    # a whole-drive walk never finishes, so it is time-boxed


class FileError(Exception):
    """Anything the caller did wrong — surfaces as 400."""


# --------------------------------------------------------------------------- log

def log_path() -> Path:
    override = current_app.config.get("ACTIVITY_DB")
    if override:
        return Path(override)
    base = Path(os.environ.get("APPDATA") or Path.home())
    return base / "FRIDAY" / "activity.db"


def _conn() -> sqlite3.Connection:
    p = log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE IF NOT EXISTS activity ("
                "id INTEGER PRIMARY KEY, at TEXT NOT NULL, action TEXT NOT NULL, "
                "path TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '')")
    return con


def log(action: str, path: str, detail: str = "") -> None:
    with _conn() as con:
        con.execute("INSERT INTO activity (at, action, path, detail) VALUES (?, ?, ?, ?)",
                    (time.strftime("%Y-%m-%d %H:%M:%S"), action, str(path), detail))


def entries(limit: int = 200) -> list[dict]:
    with _conn() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,))]


def clear_log() -> None:
    with _conn() as con:
        con.execute("DELETE FROM activity")


# --------------------------------------------------------------------------- browse

def _resolve(path: str) -> Path:
    if not path:
        raise FileError("no path given")
    try:
        return Path(path).expanduser().resolve()
    except OSError as e:
        raise FileError(str(e)) from e


def _stat(p: Path) -> dict:
    try:
        st = p.stat()
        size, mtime = st.st_size, time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))
    except OSError:      # a locked or vanished entry still belongs in the listing
        size, mtime = 0, ""
    return {"name": p.name or str(p), "path": str(p), "is_dir": p.is_dir(), "size": size, "mtime": mtime}


def roots() -> list[dict]:
    """Drive letters plus the usual user folders — the starting screen."""
    out = []
    if os.name == "nt":
        bits = ctypes.windll.kernel32.GetLogicalDrives()
        out += [{"name": f"{chr(65 + i)}:\\", "path": f"{chr(65 + i)}:\\", "is_dir": True, "size": 0, "mtime": ""}
                for i in range(26) if bits >> i & 1]
    home = Path.home()
    out += [_stat(home / n) for n in ("Desktop", "Documents", "Downloads", "Pictures")
            if (home / n).is_dir()]
    return out


def listdir(path: str) -> dict:
    p = _resolve(path)
    if not p.is_dir():
        raise FileError(f"not a folder: {p}")
    try:
        kids = sorted(p.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower()))
    except PermissionError as e:
        raise FileError(f"access denied: {p}") from e
    except OSError as e:
        raise FileError(str(e)) from e
    return {"path": str(p), "parent": str(p.parent) if p.parent != p else "",
            "entries": [_stat(c) for c in kids]}


def read_text(path: str) -> dict:
    p = _resolve(path)
    if not p.is_file():
        raise FileError(f"not a file: {p}")
    raw = p.read_bytes()[:TEXT_CAP + 1]
    truncated = len(raw) > TEXT_CAP
    raw = raw[:TEXT_CAP]
    if b"\0" in raw:
        raise FileError("binary file — no text preview")
    return {"path": str(p), "text": raw.decode("utf-8", "replace"), "truncated": truncated}


def search(root: str, q: str) -> list[dict]:
    """Name match under `root`, time-boxed — a full drive walk never finishes."""
    if not q:
        raise FileError("no search text")
    p = _resolve(root)
    needle, hits, deadline = q.lower(), [], time.monotonic() + SEARCH_SECONDS
    for folder, dirs, names in os.walk(p, onerror=lambda _e: None):
        if time.monotonic() > deadline or len(hits) >= SEARCH_CAP:
            break
        for n in dirs + names:
            if needle in n.lower():
                hits.append(_stat(Path(folder) / n))
                if len(hits) >= SEARCH_CAP:
                    break
    return hits


# --------------------------------------------------------------------------- write

def write_text(path: str, text: str) -> dict:
    p = _resolve(path)
    existed = p.exists()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    log("edit" if existed else "create", p, f"{len(text)} chars")
    return _stat(p)


def mkdir(path: str) -> dict:
    p = _resolve(path)
    if p.exists():
        raise FileError(f"already exists: {p}")
    p.mkdir(parents=True)
    log("mkdir", p)
    return _stat(p)


def rename(path: str, name: str) -> dict:
    p = _resolve(path)
    if not name or {"/", "\\", ":"} & set(name):
        raise FileError("bad name")
    target = p.with_name(name)
    if target.exists():
        raise FileError(f"already exists: {target}")
    p.rename(target)
    log("rename", p, f"to {target.name}")
    return _stat(target)


def move(path: str, to_dir: str) -> dict:
    p, d = _resolve(path), _resolve(to_dir)
    if not d.is_dir():
        raise FileError(f"not a folder: {d}")
    target = d / p.name
    if target.exists():
        raise FileError(f"already exists: {target}")
    p.rename(target)      # same volume; os.replace across volumes would need a copy
    log("move", p, f"to {target}")
    return _stat(target)


def delete(path: str) -> None:
    p = _resolve(path)
    if not p.exists():
        raise FileError(f"not found: {p}")
    _recycle(p)
    log("delete", p, "to Recycle Bin" if os.name == "nt" else "")


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint), ("pFrom", ctypes.c_wchar_p),
                ("pTo", ctypes.c_wchar_p), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", ctypes.c_int),
                ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_wchar_p)]


def _recycle(p: Path) -> None:
    if os.name != "nt":       # dev machines only; the app ships Windows-only
        if p.is_dir():
            raise FileError("folder delete needs Windows")
        p.unlink()
        return
    FO_DELETE, ALLOWUNDO, NOCONFIRM, SILENT, NOERRORUI = 3, 0x0040, 0x0010, 0x0004, 0x0400
    op = _SHFILEOPSTRUCTW(None, FO_DELETE, f"{p}\0\0", None,
                          ALLOWUNDO | NOCONFIRM | SILENT | NOERRORUI, 0, None, None)
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if rc:
        raise FileError(f"delete failed (code {rc})")
