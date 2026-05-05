"""SQLAlchemy engine и фабрика сессий."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

_engine = create_engine(
    settings.database_url,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, class_=Session, future=True)


def get_engine():
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """Контекст-менеджер сессии с автокоммитом и откатом при ошибке."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
