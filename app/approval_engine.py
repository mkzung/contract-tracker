"""Движок агрегации статусов согласования.

Задача: прогнать неклассифицированные сообщения через LLM, обновить Response
и пересчитать итоговый статус каждого треда.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import session_scope
from app.llm_classifier import classify
from app.logging_conf import get_logger
from app.models import Message, Participant, Response, ResponseKind, Thread, ThreadStatus

log = get_logger(__name__)


def _classify_unclassified(session: Session) -> int:
    """Классифицирует все письма без метки. Возвращает количество обработанных."""
    pending = (
        session.execute(
            select(Message).where(Message.classification.is_(None)).order_by(Message.sent_at)
        )
        .scalars()
        .all()
    )

    count = 0
    for msg in pending:
        # Корневое письмо (инициатор) обычно не нуждается в LLM — это "info".
        is_root_like = msg.thread_id and msg.thread.root_message_id == msg.message_id
        if is_root_like:
            msg.classification = ResponseKind.INFO
            msg.classification_confidence = 1.0
            msg.classification_reason = "Корневое письмо треда"
            count += 1
            continue

        try:
            result = classify(
                subject=msg.subject,
                from_name=msg.from_name,
                from_addr=msg.from_addr,
                body_text=msg.body_text,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("classify.error", message_id=msg.message_id, error=str(exc))
            continue

        msg.classification = result.kind
        msg.classification_confidence = result.confidence
        msg.classification_reason = result.reason
        count += 1
    return count


def _rebuild_responses(session: Session, thread: Thread) -> None:
    """Пересобирает актуальные Response (последний ответ каждого согласованта)."""
    # Удалим старые и пересоздадим — просто и дёшево на MVP
    for r in list(thread.responses):
        session.delete(r)

    # Отсортированы по sent_at в relationship, берём последний ответ от каждого отправителя
    latest: dict[str, Message] = {}
    for m in thread.messages:
        if m.classification in {None, ResponseKind.INFO}:
            continue
        latest[m.from_addr] = m  # позднее письмо перезапишет раннее

    for from_addr, m in latest.items():
        p = session.execute(
            select(Participant).where(Participant.email == from_addr)
        ).scalar_one_or_none()
        if not p:
            continue
        session.add(
            Response(
                thread_id=thread.id,
                participant_id=p.id,
                message_id=m.id,
                kind=m.classification,
                responded_at=m.sent_at,
                snippet=(m.body_text or "")[:500],
            )
        )


def _recompute_thread_status(thread: Thread) -> ThreadStatus:
    """Определяет итоговый статус треда по набору Response."""
    kinds = {r.kind for r in thread.responses}

    # Если есть корректировка от инициатора — цикл открыт заново
    if ResponseKind.CORRECTION in kinds:
        return ThreadStatus.CORRECTED
    if ResponseKind.OBJECTION in kinds:
        return ThreadStatus.OBJECTIONS

    # Silent approval по дедлайну
    if thread.deadline_at and datetime.now(timezone.utc) > thread.deadline_at.replace(
        tzinfo=thread.deadline_at.tzinfo or timezone.utc
    ):
        if not (kinds - {ResponseKind.APPROVAL, ResponseKind.CONDITIONAL, ResponseKind.INFO}):
            return ThreadStatus.APPROVED_SILENT

    # Если остались только approvals/conditional — ждём, пока все отметятся
    # Без списка ожидаемых согласовантов (его строим отдельно в дашборде) — оставляем PENDING
    return ThreadStatus.PENDING


def tick() -> None:
    """Один проход: классификация + пересборка Response + обновление статусов."""
    with session_scope() as s:
        classified = _classify_unclassified(s)
    if classified:
        log.info("engine.classified", count=classified)

    with session_scope() as s:
        threads = s.execute(select(Thread)).scalars().all()
        for t in threads:
            if t.status == ThreadStatus.CLOSED:
                continue
            _rebuild_responses(s, t)
            t.status = _recompute_thread_status(t)


if __name__ == "__main__":
    from app.logging_conf import configure_logging

    configure_logging()
    tick()
