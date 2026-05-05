"""Создание таблиц в БД. Идемпотентно."""

from __future__ import annotations

from pathlib import Path

from app.config import settings
from app.database import get_engine
from app.models import Base


def main() -> None:
    # Гарантируем, что директория для SQLite-файла существует
    if settings.database_url.startswith("sqlite:///"):
        db_path = Path(settings.database_url.replace("sqlite:///", "", 1))
        db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = get_engine()
    Base.metadata.create_all(engine)
    print(f"OK: таблицы созданы в {settings.database_url}")


if __name__ == "__main__":
    main()
