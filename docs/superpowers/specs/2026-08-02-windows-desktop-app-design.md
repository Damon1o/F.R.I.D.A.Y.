# Windows 11 desktop app — design

Ship F.R.I.D.A.Y. as a downloadable Windows 11 installer. Decisions taken:
Neon stays the database (app needs internet, same data as friday-ts.vercel.app),
unsigned Inno Setup installer, GitHub-releases update check.

## Shape

No rewrite. The desktop app is the existing Flask app, started on localhost by a
launcher, displayed in a native frameless WebView2 window (pywebview).

```
friday.exe (PyInstaller onedir)
  ├─ picks a free port
  ├─ serves create_app({"DESKTOP": True}) with waitress on 127.0.0.1:<port>
  ├─ opens a frameless pywebview window on that URL (the page draws the title bar)
  └─ window closed ⇒ os._exit(0)
```

**Revised (same day).** The first cut used Edge app-mode (`msedge --app=`) to keep
the Web Speech API, and shipped that way. It looked like a browser window: Edge's
frame, Edge's icon, Edge's taskbar grouping. The native window replaces it, and
voice moves off the browser instead of the browser being chosen for voice:

- WebView2 exposes `webkitSpeechRecognition`, but the service behind it is
  Chrome-only. Dictation and speech now go to the bundled engines
  (`vendor/voice`: whisper.cpp + piper) through `/api/voice/stt` and `/api/voice/tts`
  — the offline path `voice-web.js` already had. It is local, so it also works
  with no network.
- Mic in WebView2 needs two things: a **secure context** (http://127.0.0.1 is one;
  a `html=` document is not — `getUserMedia` there never settles), and a host-side
  `PermissionRequested` handler, which `desktop/main.py` attaches on the UI thread.
  Result: no permission prompt, ever.
- Cost: ~145 MB of voice binaries in the installer (26 MB → ~170 MB). Accepted for
  a real app window and fully offline voice.
- Edge app-mode remains the fallback when pywebview or the WebView2 runtime is
  absent; that path keeps the in-app quit button and `--force-dark-mode`.

Not Electron: same window quality, but a Node build step (the project has none)
and its own runtime on top of the WebView2 one already on every Windows 11 box.

ponytail: skipped a tray icon and a single-instance mutex. Add a tray icon when
the window is closed accidentally and it matters.

## Work

### 1. Launcher — `desktop/main.py` (~40 lines)

- Free port: `socket.socket().bind(("127.0.0.1", 0))`.
- `waitress.serve(create_app(), ...)` on a daemon thread (`waitress` added to
  `requirements.txt`; Flask's dev server is single-threaded and prints a
  warning banner).
- Locate Edge: `%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe`, then
  `shutil.which("msedge")`. Neither found ⇒ `webbrowser.open(url)` fallback.
- `subprocess.run([edge, f"--app={url}", f"--user-data-dir={profile}"])`, then
  `os._exit(0)`.
- Frozen-path handling: `sys._MEIPASS` as the Flask root when `sys.frozen`.

### 2. Secrets — `%APPDATA%\FRIDAY\.env`

`config.py` currently does a bare `load_dotenv()` (CWD-relative — wrong once
installed). Change to `load_dotenv(APPDATA/.env)` first, then repo `.env` as
fallback for dev. Installer does not ship secrets; first run with an empty
`DATABASE_URL` writes a template `.env` and opens it in Notepad with a one-line
message. DeepSeek/Comms keys go in the same file.

### 3. `init_db()` on every boot

`create_app()` runs `db.init_db()`, which needs Neon reachable at startup. On a
laptop opened offline that crashes the launcher. Guard it: catch
`psycopg.OperationalError`, show a "no connection" page instead of a traceback.

### 4. PyInstaller — `friday.spec`

- `onedir` (onefile unpacks ~60 MB to temp on every launch — slow start).
- `datas`: `templates/`, `static/` (includes `static/vendor/ort`,
  `static/vendor/wakeword`, `static/vendor/lucide`), `schema.sql`,
  `skills-lock.json`.
- `hiddenimports`: page blueprints are imported inside `create_app()`, so
  PyInstaller's static analysis finds them; verify with a smoke run, add any
  missing `pages.*` modules.
- `icon=static/images/friday.ico` (convert from `friday.svg`).
- Console window off (`console=False`).

### 5. Installer — `installer/friday.iss` (Inno Setup)

- `PrivilegesRequired=lowest`, install to
  `{localappdata}\Programs\FRIDAY` — no UAC prompt.
- Start-menu entry, optional desktop shortcut, uninstaller.
- `AppVersion` read from a single `VERSION` constant also exposed by the app
  (used by the update check).
- Unsigned: first launch shows SmartScreen "Windows protected your PC" →
  *More info* → *Run anyway*. Documented in the README.

### 6. Update check

`GET https://api.github.com/repos/<owner>/friday/releases/latest` on boot, in a
thread, 3 s timeout, failures ignored. Newer `tag_name` than `VERSION` ⇒ the
existing toast component shows "Update available" linking to the release page.
No silent download, no updater service.

### 7. Build script — `scripts/build_windows.ps1`

`pyinstaller friday.spec` → `iscc installer/friday.iss` → output
`dist/FRIDAY-Setup-<version>.exe`. Smoke test: launch the built exe, confirm the
dashboard renders, mic button works, and a task can be created.

## Not doing

- Code signing (needs a purchased cert; SmartScreen warning accepted).
- MSIX / Store.
- Offline mode (Neon is the store of record; SQLite port is a separate project).
- Auto-download/apply of updates.
