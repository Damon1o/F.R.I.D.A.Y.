"""App configuration, read from environment (.env via python-dotenv)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


class Config:
    # Phase 1: local single-user app.
    DB_PATH = os.environ.get("KIKO_DB_PATH", str(BASE_DIR / "kiko.db"))
    HOST = os.environ.get("KIKO_HOST", "127.0.0.1")
    PORT = int(os.environ.get("KIKO_PORT", "5000"))
    # ponytail: later-phase keys (DeepSeek etc.) live in .env; not read until Phase 2.
