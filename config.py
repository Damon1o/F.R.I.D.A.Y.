"""App configuration, read from environment (.env via python-dotenv)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


class Config:
    # Cloud (Spec A): Postgres via psycopg. Pooled Neon URL in prod.
    DATABASE_URL = os.environ.get("DATABASE_URL", "")
    HOST = os.environ.get("FRIDAY_HOST", "127.0.0.1")
    PORT = int(os.environ.get("FRIDAY_PORT", "5000"))
    # Phase 2 — DeepSeek. Missing key is not fatal; the agent emits a friendly error frame.
    DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
    # Spec B — voice endpoint shared secret. Empty ⇒ /api/voice refuses every request (fail closed).
    VOICE_TOKEN = os.environ.get("VOICE_TOKEN", "")
    # Hard cap on any request body (Werkzeug rejects with 413 during parsing, before buffering).
    # A little above the voice audio cap (2 MB) to allow multipart overhead.
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024 + 64 * 1024
