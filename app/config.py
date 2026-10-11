"""Configuration from environment / .env. Keys are NEVER hardcoded."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str = os.environ.get(
        "DATABASE_URL", "postgresql://ada:ada@localhost:5432/sales_db"
    )
    llm_provider: str = os.environ.get("LLM_PROVIDER", "gemini").lower()
    google_api_key: str = os.environ.get("GOOGLE_API_KEY", "")
    gemini_model: str = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    groq_api_key: str = os.environ.get("GROQ_API_KEY", "")
    groq_model: str = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    max_sql_retries: int = int(os.environ.get("MAX_SQL_RETRIES", "3"))


settings = Settings()
