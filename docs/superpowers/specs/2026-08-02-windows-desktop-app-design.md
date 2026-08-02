# Windows 11 desktop app — design

Ship F.R.I.D.A.Y. as a downloadable Windows 11 installer. Decisions taken:
Neon stays the database (app needs internet, same data as friday-ts.vercel.app),
unsigned Inno Setup installer, GitHub-releases update check.

## Shape

No rewrite. The desktop app is the existing Flask app, started on localhost by a
launcher, displayed in a chrome-less Edge window.

```
friday.exe (PyInstaller onedir)
  ├─ picks a free port
  ├─ serves create_app() with waitress on 127.0.0.1:<port>
  ├─ launches msedge.exe --app=http://127.0.0.1:<port> --user-data-dir=%LOCALAPPDATA%\FRIDAY\profile
  └─ waits on the Edge process; window closed ⇒ server exits
```

Why Edge app-mode and not pywebview/Electron:

- pywebview's WebView2 host has no Web Speech API (`SpeechRecognition`,
  `speechSynthesis`) — `static/js/voice-web.js` and the wake word UX would
  silently degrade, and mic permission in WebView2 needs a permission handler.
  Edge app-mode is real Chromium: mic, Web Speech, and openWakeWord's
  `getUserMedia` all work as they do today.
- Edge ships with Windows 11 — zero bundled runtime, ~35 MB install instead of
  ~180 MB (Electron) .
- A dedicated `--user-data-dir` makes it a separate process we can `wait()` on,
  and mic permission is granted once and persists in that profile.

ponytail: skipped a tray icon, single-instance mutex, and offline voice
binaries. Add a tray icon when the window is closed accidentally and it matters.

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
