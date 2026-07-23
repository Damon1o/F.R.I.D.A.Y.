"""App configuration, read from environment (.env via python-dotenv)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


class Config:
    # Phase 1: local single-user app.
    DB_PATH = os.environ.get("FRIDAY_DB_PATH", str(BASE_DIR / "friday.db"))
    HOST = os.environ.get("FRIDAY_HOST", "127.0.0.1")
    PORT = int(os.environ.get("FRIDAY_PORT", "5000"))
    # Phase 2 — F.R.I.D.A.Y. assistant (DeepSeek, OpenAI-compatible). Missing key is not fatal;
    # the agent emits a friendly error frame instead of crashing.
    DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
