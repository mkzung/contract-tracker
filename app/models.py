"""Модели БД: Thread, Message, Participant, Response."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ThreadStatus(str, enum.Enum):
    """Статус треда согласования договора."""

    PENDING = "pending"           # идёт согласование
    APPROVED = "approved"         # все согласовали
    APPROVED_SILENT = "silent"    # дедлайн истёк, все непротестовавшие считаются согласовавшими
    OBJECTIONS = "objections"     # есть замечания, ждут исправления
    CORRECTED = "corrected"       # была корректировка, новый круг
    CLOSED = "closed"             # закрыт вручную


class ResponseKind(str, enum.Enum):
    """Классификация ответа согласованта."""

    APPROVAL = "approval"
    CONDITIONAL = "conditional"   # "в остальном согласовано, но поправьте ..."
    OBJECTION = "objection"
    QUESTION = "question"
    CORRECTION = "correction"     # отправитель прислал исправленную версию
    INFO = "info"                 # просто информация, не решение
    UNKNOWN = "unknown"


class Thread(Base):
    """Тред согласования одного договора."""

    __tablename__ = "threads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    root_message_id: Mapped[str] = mapped_column(String(512), unique=True, index=True)

    # Разобранная из темы информация
    subject_original: Mapped[str] = mapped_column(String(1024))
    contractor: Mapped[str | None] = mapped_column(String(512), index=True)
    subject_matter: Mapped[str | None] = mapped_column(String(1024))
    region: Mapped[str | None] = mapped_column(String(256), index=True)
    object_name: Mapped[str | None] = mapped_column(String(512), index=True)

    # Бизнес-данные (опционально, через связь с Excel-справочником)
    contract_amount: Mapped[float | None] = mapped_column()
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[ThreadStatus] = mapped_column(
        Enum(ThreadStatus, native_enum=False), default=ThreadStatus.PENDING, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    messages: Mapped[list[Message]] = relationship(
        back_populates="thread", cascade="all, delete-orphan", order_by="Message.sent_at"
    )
    responses: Mapped[list[Response]] = relationship(
        back_populates="thread", cascade="all, delete-orphan"
    )


class Message(Base):
    """Отдельное письмо в треде."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"), index=True)

    message_id: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    in_reply_to: Mapped[str | None] = mapped_column(String(512), index=True)
    references: Mapped[list[str] | None] = mapped_column(JSON)

    subject: Mapped[str] = mapped_column(String(1024))
    from_addr: Mapped[str] = mapped_column(String(256), index=True)
    from_name: Mapped[str | None] = mapped_column(String(256))
    to_addrs: Mapped[list[str]] = mapped_column(JSON, default=list)
    cc_addrs: Mapped[list[str]] = mapped_column(JSON, default=list)

    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    body_text: Mapped[str] = mapped_column(Text)

    # Classified via LLM (кэш)
    classification: Mapped[ResponseKind | None] = mapped_column(
        Enum(ResponseKind, native_enum=False)
    )
    classification_confidence: Mapped[float | None] = mapped_column()
    classification_reason: Mapped[str | None] = mapped_column(Text)

    thread: Mapped[Thread] = relationship(back_populates="messages")


class Participant(Base):
    """Согласовант (уникальный сотрудник по email)."""

    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(256))
    full_name: Mapped[str | None] = mapped_column(String(256))
    role: Mapped[str | None] = mapped_column(String(128))


class Response(Base):
    """Итоговый вклад одного согласованта в один тред (последний его ответ)."""

    __tablename__ = "responses"
    __table_args__ = (UniqueConstraint("thread_id", "participant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))

    kind: Mapped[ResponseKind] = mapped_column(Enum(ResponseKind, native_enum=False))
    responded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snippet: Mapped[str | None] = mapped_column(Text)

    thread: Mapped[Thread] = relationship(back_populates="responses")
    participant: Mapped[Participant] = relationship()
