# PyInstaller spec for the Windows desktop build. onedir, not onefile: onefile unpacks the
# whole static/ tree to a temp dir on every launch.
#
# Data files land at the bundle root, which is what the app already expects — app.py,
# core/db.py and friends resolve paths from `Path(__file__).parent`, and PyInstaller points
# that at sys._MEIPASS.
from PyInstaller.utils.hooks import collect_submodules

datas = [
    ("templates", "templates"),
    ("static", "static"),
    ("schema.sql", "."),
    ("skills-lock.json", "."),
]

# Blueprints are imported inside create_app(), so PyInstaller's static analysis never sees
# them. Collect the page packages wholesale rather than listing every module by hand.
hiddenimports = collect_submodules("pages") + collect_submodules("core") + ["psycopg", "waitress"]

a = Analysis(
    ["desktop/main.py"],
    pathex=["."],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "playwright", "tkinter"],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="FRIDAY",
    console=False,
    icon="static/images/friday.ico",
)
COLLECT(exe, a.binaries, a.datas, name="FRIDAY")
