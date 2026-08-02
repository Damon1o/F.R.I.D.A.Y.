"""Windows desktop entrypoint. Serves the Flask app on a private localhost port and shows
it in a native, frameless WebView2 window (pywebview) — the app draws its own title bar.

WebView2 has no Web Speech API, so dictation and speech would die with the browser window.
They do not: `voice-web.js` falls back to the offline engine, which posts audio to
/api/voice/stt and /api/voice/tts — whisper.cpp and piper, bundled in vendor/voice.

Two WebView2 details that matter:

* the page is served over http://127.0.0.1, a secure context — `getUserMedia` refuses to
  even ask outside one, which reads as a hang rather than an error;
* WebView2 raises PermissionRequested for the mic and waits. Nothing in the window can
  answer it, so the host allows it (see `_allow_permissions`) and no prompt is ever shown.

Edge app-mode is still the fallback when pywebview or the WebView2 runtime is missing.
"""
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

# PyInstaller unpacks the data files to _MEIPASS; from a checkout it is the repo root.
BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
ICON = BASE / "static" / "images" / "friday.ico"
PROFILE = Path(os.environ["LOCALAPPDATA"]) / "FRIDAY" / "profile"      # Edge fallback profile
WEBVIEW_DIR = Path(os.environ["LOCALAPPDATA"]) / "FRIDAY" / "webview"  # WebView2 user data
EDGE_CANDIDATES = (
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
)

EDGE_PID = 0
WINDOW = None


def _quit() -> None:
    if WINDOW is not None:
        try:
            WINDOW.destroy()
        except Exception:      # already closing
            pass
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


class Titlebar:
    """Exposed to the page as `window.pywebview.api` — the buttons in our own title bar."""

    def minimize(self):
        WINDOW.minimize()

    def maximize(self):
        # pywebview has no "is maximized" flag; the page tracks which way it last went.
        WINDOW.maximize()

    def restore(self):
        WINDOW.restore()

    def close(self):
        _quit()


def _allow_permissions(window) -> None:
    """Say yes to the mic on the host side. CoreWebView2 lives on the UI thread and appears
    a beat after the window does, so this polls and marshals with Invoke."""
    from System import Action
    from Microsoft.Web.WebView2.Core import CoreWebView2PermissionState
    from webview.platforms.winforms import BrowserView

    form = None
    for _ in range(60):
        form = BrowserView.instances.get(window.uid)
        if form is not None and getattr(form, "webview", None) is not None:
            break
        time.sleep(0.25)
    if form is None:
        return

    done = {}

    def attach():
        core = form.webview.CoreWebView2
        if core is None:
            return

        def granted(_sender, args):
            args.State = CoreWebView2PermissionState.Allow

        core.PermissionRequested += granted
        done["ok"] = True

    for _ in range(60):
        form.Invoke(Action(attach))
        if done:
            return
        time.sleep(0.25)


def _native_window(url: str, app) -> bool:
    """Frameless WebView2 window. False ⇒ pywebview or the runtime is unavailable."""
    try:
        import webview
    except ImportError:
        return False

    # The page draws the title bar only in this window; the Edge fallback has its own.
    app.config["NATIVE"] = True
    global WINDOW
    if os.environ.get("FRIDAY_DEVTOOLS"):     # opt-in: attach a debugger to the real window
        webview.settings["REMOTE_DEBUGGING_PORT"] = 9223
    WEBVIEW_DIR.mkdir(parents=True, exist_ok=True)
    WINDOW = webview.create_window(
        "F.R.I.D.A.Y.", url, frameless=True, easy_drag=False,
        width=1440, height=920, min_size=(960, 640), background_color="#121414",
        js_api=Titlebar(),
    )

    def ready(window):
        _allow_permissions(window)
        from desktop import winicon
        winicon.apply(os.getpid(), str(ICON))   # our own window: title bar + taskbar icon

    try:
        webview.start(ready, WINDOW, private_mode=False, storage_path=str(WEBVIEW_DIR))
    except Exception:      # no WebView2 runtime on this machine
        return False
    return True


def main() -> None:
    if not ensure_env():
        return

    from waitress import serve

    from app import create_app
    from desktop import winicon
    from desktop.update import check_async

    app = create_app({"DESKTOP": True})
    check_async(app)
    port = free_port()
    url = f"http://127.0.0.1:{port}/"

    @app.post("/api/quit")
    def quit_app():
        threading.Timer(0.15, _quit).start()   # let the response flush first
        return "", 204

    threading.Thread(target=serve, args=(app,), kwargs={"host": "127.0.0.1", "port": port, "threads": 8},
                     daemon=True).start()

    if _native_window(url, app):
        os._exit(0)

    edge = find_edge()
    if edge:
        PROFILE.mkdir(parents=True, exist_ok=True)
        global EDGE_PID
        # --force-dark-mode: the frame is Edge's here, and its light theme puts a white
        # strip above a black app. This themes browser UI only, not page content.
        proc = subprocess.Popen([edge, f"--app={url}", f"--user-data-dir={PROFILE}", "--force-dark-mode"])
        EDGE_PID = proc.pid
        threading.Thread(target=winicon.apply, args=(proc.pid, str(ICON)), daemon=True).start()
        proc.wait()
    else:
        # No Edge either: fall back to the default browser and block on stdin so the
        # server stays up until the console window is closed.
        webbrowser.open(url)
        input()
    os._exit(0)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    main()
