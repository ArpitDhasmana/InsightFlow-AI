"""Application settings loaded from environment / .env file."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB = f"sqlite:///{(_PROJECT_ROOT / 'insightflow.db').as_posix()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = _DEFAULT_DB
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key.strip())


settings = Settings()
