"""Windows desktop entrypoint. Serves the Flask app on a private localhost port and
shows it in a chrome-less Edge window.

Edge app-mode instead of a WebView2 host (pywebview): WebView2 has no Web Speech API,
which `static/js/voice-web.js` and the wake word depend on. `--user-data-dir` gives the
window its own process (so we can wait on it) and its own permission store (so the mic
prompt is answered once, ever).
"""
import os
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

# PyInstaller unpacks the data files to _MEIPASS; from a checkout it is the repo root.
BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
ICON = BASE / "static" / "images" / "friday.ico"
PROFILE = Path(os.environ["LOCALAPPDATA"]) / "FRIDAY" / "profile"
EDGE_CANDIDATES = (
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
)


EDGE_PID = 0


def _quit() -> None:
    if EDGE_PID:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(EDGE_PID)],
                       creationflags=subprocess.CREATE_NO_WINDOW)
    os._exit(0)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def find_edge() -> str | None:
    for p in EDGE_CANDIDATES:
        if p.exists():
            return str(p)
    return shutil.which("msedge")


ENV_TEMPLATE = """# F.R.I.D.A.Y. — desktop settings. Restart the app after editing.
DATABASE_URL=
DEEPSEEK_API_KEY=
COMMS_OSIS_API=
VOICE_TOKEN=
"""


def ensure_env() -> bool:
    """Write a settings template on first run. False ⇒ nothing to run yet."""
    env = Path(os.environ["APPDATA"]) / "FRIDAY" / ".env"
    if env.exists():
        return True
    if (Path(__file__).resolve().parent.parent / ".env").exists():
        return True  # running from a checkout; repo .env wins
    env.parent.mkdir(parents=True, exist_ok=True)
    env.write_text(ENV_TEMPLATE, encoding="utf-8")
    subprocess.Popen(["notepad.exe", str(env)])
    return False


def main() -> None:
    if not ensure_env():
        return

    from waitress import serve

    from app import create_app
    from desktop import winicon
    from desktop.update import check_async

    app = create_app({"DESKTOP": True})  # shows the in-app quit button
    check_async(app)
    port = free_port()
    url = f"http://127.0.0.1:{port}/"

    @app.post("/api/quit")
    def quit_app():
        # Kill the whole Edge tree, not just the process we spawned: msedge.exe hands the
        # window to a child and returns, so terminate() would leave the window on screen.
        threading.Timer(0.15, _quit).start()  # let the response flush first
        return "", 204

    threading.Thread(target=serve, args=(app,), kwargs={"host": "127.0.0.1", "port": port, "threads": 8},
                     daemon=True).start()

    edge = find_edge()
    if edge:
        PROFILE.mkdir(parents=True, exist_ok=True)
        global EDGE_PID
        # --force-dark-mode: the window frame is Edge's, and its default light theme puts a
        # white strip above a black app. This only themes browser UI, not page content.
        proc = subprocess.Popen([edge, f"--app={url}", f"--user-data-dir={PROFILE}", "--force-dark-mode"])
        EDGE_PID = proc.pid
        # The window is Edge's, so it wears Edge's icon until we retag it — see winicon.
        threading.Thread(target=winicon.apply, args=(proc.pid, str(ICON)), daemon=True).start()
        proc.wait()
    else:
        # No Edge (unusual on Windows 11): fall back to the default browser and block on stdin
        # so the server stays up until the console window is closed.
        webbrowser.open(url)
        input()
    os._exit(0)  # waitress' thread is a daemon, but Edge leaves helper threads around


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    main()
