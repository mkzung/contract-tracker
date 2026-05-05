"""Настройки приложения из переменных окружения."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # IMAP
    imap_host: str = "imap.mail.ru"
    imap_port: int = 993
    imap_user: str
    imap_password: str
    imap_folder: str = "INBOX"
    imap_poll_interval_seconds: int = 300

    # DB
    database_url: str = "sqlite:///./data/tracker.db"

    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-5.4"

    # Логи
    log_level: str = "INFO"
    log_file: str | None = None

    # Дашборд
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8501

    # Парсинг темы
    subject_prefix: str = "На согласование"


settings = Settings()  # type: ignore[call-arg]
