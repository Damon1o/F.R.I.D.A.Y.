import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///assistant.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TOKEN_BUDGET_WARNING = int(os.environ.get("TOKEN_BUDGET_WARNING", "50000"))
