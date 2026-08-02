"""App configuration, read from environment (.env via python-dotenv)."""
import os
from pathlib import Path

from dotenv import load_dotenv

# Installed desktop app: settings live in %APPDATA%\FRIDAY\.env (the working directory of
# an installed exe is not the repo). First file wins — a checkout's .env still overrides
# nothing, load_dotenv never replaces a variable already set.
if os.name == "nt":
    load_dotenv(Path(os.environ.get("APPDATA", "")) / "FRIDAY" / ".env")
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
VERSION = "1.0.0"


class Config:
    # Cloud (Spec A): Postgres via psycopg. Pooled Neon URL in prod.
    DATABASE_URL = os.environ.get("DATABASE_URL", "")
    HOST = os.environ.get("FRIDAY_HOST", "127.0.0.1")
    PORT = int(os.environ.get("FRIDAY_PORT", "5000"))
    # Phase 2 — DeepSeek. Missing key is not fatal; the agent emits a friendly error frame.
    DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
    # Second opinion. SAT questions are only useful if the answer key is right, and
    # the writer model does get its own key wrong — so a different model solves every
    # question independently and disagreements are thrown away (pages/sat/models.py).
    DEEPSEEK_VERIFY_MODEL = os.environ.get("DEEPSEEK_VERIFY_MODEL", "deepseek-reasoner")
    # Comms by Osis — outbound SMS/iMessage. Empty ⇒ the send_sms tool returns a friendly error.
    COMMS_API_KEY = os.environ.get("COMMS_OSIS_API", "")
    # Cron shared secret (Vercel sends it as a bearer token). Empty ⇒ /api/cron/* refuses all.
    CRON_SECRET = os.environ.get("CRON_SECRET", "")
    # Spec B — voice endpoint shared secret. Empty ⇒ /api/voice refuses every request (fail closed).
    VOICE_TOKEN = os.environ.get("VOICE_TOKEN", "")
    # Hard cap on any request body (Werkzeug rejects with 413 during parsing, before buffering).
    # A little above the voice audio cap (2 MB) to allow multipart overhead.
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024 + 64 * 1024
