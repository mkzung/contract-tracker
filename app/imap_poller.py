"""Поллер IMAP: читает новые письма, сохраняет в БД, привязывает к тредам."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from imap_tools import AND, MailBox
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import session_scope
from app.logging_conf import configure_logging, get_logger
from app.models import Message, Participant, ResponseKind, Thread, ThreadStatus
from app.subject_parser import SubjectInfo, parse_subject
from app.thread_parser import ParsedMessage, find_root_message_id, parse_message

log = get_logger(__name__)


def _get_or_create_thread(
    session: Session, pm: ParsedMessage, subject_info: SubjectInfo
) -> Thread | None:
    """Находит тред по root_message_id либо создаёт новый (если пришло стартовое письмо).

    Возвращает None, если это не 'На согласование:' и треда мы ещё не знаем.
    """
    root_id = find_root_message_id(pm)

    existing = session.execute(
        select(Thread).where(Thread.root_message_id == root_id)
    ).scalar_one_or_none()
    if existing:
        return existing

    # Треда нет. Создаём только если это явно стартовое письмо с корректной темой.
    if not subject_info.is_approval_subject:
        return None

    thread = Thread(
        root_message_id=root_id,
        subject_original=pm.subject,
        contractor=subject_info.contractor,
        subject_matter=subject_info.subject_matter,
        region=subject_info.region,
        object_name=subject_info.object_name,
        status=ThreadStatus.PENDING,
    )
    session.add(thread)
    session.flush()
    log.info(
        "thread.created",
        thread_id=thread.id,
        contractor=thread.contractor,
        region=thread.region,
        object=thread.object_name,
    )
    return thread


def _upsert_participant(session: Session, email: str, name: str | None) -> Participant:
    p = session.execute(
        select(Participant).where(Participant.email == email)
    ).scalar_one_or_none()
    if p:
        if name and not p.display_name:
            p.display_name = name
        return p
    p = Participant(email=email, display_name=name)
    session.add(p)
    session.flush()
    return p


def _save_message(
    session: Session, thread: Thread, pm: ParsedMessage
) -> Message | None:
    """Сохраняет письмо, если ещё не сохраняли (идемпотентно по message_id)."""
    if not pm.message_id:
        log.warning("message.no_id", subject=pm.subject)
        return None

    exists = session.execute(
        select(Message).where(Message.message_id == pm.message_id)
    ).scalar_one_or_none()
    if exists:
        return exists

    # Отправитель -> Participant
    _upsert_participant(session, pm.from_addr, pm.from_name)

    msg = Message(
        thread_id=thread.id,
        message_id=pm.message_id,
        in_reply_to=pm.in_reply_to,
        references=pm.references,
        subject=pm.subject,
        from_addr=pm.from_addr,
        from_name=pm.from_name,
        to_addrs=pm.to_addrs,
        cc_addrs=pm.cc_addrs,
        sent_at=pm.sent_at or datetime.now(timezone.utc),
        body_text=pm.body_text,
    )
    session.add(msg)
    session.flush()

    # Все получатели -> Participant
    for addr in set(pm.to_addrs) | set(pm.cc_addrs):
        if addr:
            _upsert_participant(session, addr, None)

    log.info("message.saved", thread_id=thread.id, message_id=pm.message_id, from_=pm.from_addr)
    return msg


def process_new_messages(
    *, since: datetime | None = None, limit: int | None = None, mark_seen: bool = False
) -> int:
    """Одноразовый проход по IMAP: скачивает письма с темой 'На согласование' (с учётом Re:).

    Возвращает количество обработанных новых писем.
    """
    criteria = AND(subject=settings.subject_prefix)
    if since:
        criteria = AND(criteria, date_gte=since.date())

    count = 0
    with MailBox(settings.imap_host, port=settings.imap_port).login(
        settings.imap_user, settings.imap_password, initial_folder=settings.imap_folder
    ) as mailbox:
        # Mail.ru требует UTF-8 для не-ASCII subject в SEARCH. imap-tools 1.12
        # не пропускает charset через .fetch(), делаем split: uids с charset,
        # затем fetch по этим uids.
        uids = mailbox.uids(criteria, charset="UTF-8")
        if limit:
            uids = list(uids)[-limit:] if not False else list(uids)[:limit]
        if not uids:
            log.debug("poller.no_new_messages", criteria=str(criteria))
            return 0
        fetched = mailbox.fetch(
            AND(uid=",".join(uids)),
            mark_seen=mark_seen,
            bulk=False,
            headers_only=False,
        )
        for msg in fetched:
            pm = parse_message(msg)
            si = parse_subject(pm.subject)

            with session_scope() as s:
                thread = _get_or_create_thread(s, pm, si)
                if thread is None:
                    log.debug("skip.no_thread", subject=pm.subject)
                    continue
                _save_message(s, thread, pm)
            count += 1
    return count


def run_forever() -> None:
    configure_logging()
    log.info("poller.start", folder=settings.imap_folder, interval=settings.imap_poll_interval_seconds)
    while True:
        try:
            processed = process_new_messages()
            log.info("poller.cycle", processed=processed)
        except Exception as exc:  # noqa: BLE001
            log.exception("poller.error", error=str(exc))
        time.sleep(settings.imap_poll_interval_seconds)


if __name__ == "__main__":
    run_forever()
