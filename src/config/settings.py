from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

IngestionTime = Literal["hour", "day", "week", "month", "all"]
IngestionSort = Literal["hot", "new", "top", "rising"]
PublishModeSetting = Literal["manual-approval", "semi-auto"]


class Settings(BaseSettings):
    app_env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"

    database_url: str = "sqlite+aiosqlite:///./moltbook.db"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b"
    translation_language: str = ""
    threads_language: str = "en"

    moltbook_api_base_url: str = "https://api.moltbook.internal"
    moltbook_api_token: str = "local-test-token"

    threads_api_base_url: str = "https://graph.threads.net"
    threads_api_token: str = "local-test-token"
    threads_account_id: str = "local-test-account"

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_webhook_url: str = ""
    telegram_daily_summary_hour: int = 22
    telegram_daily_summary_timezone: str = "UTC"

    publish_mode: PublishModeSetting = "manual-approval"
    max_publish_per_day: int = 5
    ingestion_time: IngestionTime = "hour"
    ingestion_limit: int = Field(default=20, ge=1, le=200)
    ingestion_sort: IngestionSort = "top"
    review_min_score: float = Field(default=3.5, ge=0.0, le=5.0)
    auto_publish_min_score: float = Field(default=4.0, ge=0.0, le=5.0)

    ingestion_interval_minutes: int = 60
    publish_poll_minutes: int = 5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("max_publish_per_day")
    @classmethod
    def validate_publish_limit(cls, value: int) -> int:
        if value < 0 or value > 5:
            raise ValueError("max_publish_per_day must be between 0 and 5")
        return value

    @field_validator("telegram_daily_summary_hour")
    @classmethod
    def validate_telegram_daily_summary_hour(cls, value: int) -> int:
        if value < 0 or value > 23:
            raise ValueError("telegram_daily_summary_hour must be between 0 and 23")
        return value

    @field_validator("ingestion_interval_minutes", "publish_poll_minutes")
    @classmethod
    def validate_positive_interval(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("intervals must be greater than zero")
        return value

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
