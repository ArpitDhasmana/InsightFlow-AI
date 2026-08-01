"""Application settings loaded from environment / .env file."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB = f"sqlite:///{(_PROJECT_ROOT / 'insightflow.db').as_posix()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_PROJECT_ROOT / ".env"), extra="ignore")

    database_url: str = _DEFAULT_DB
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-lite"
    gemini_fallback_model: str = "gemini-2.5-flash"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.gemini_api_key.strip())


settings = Settings()
