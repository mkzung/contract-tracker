"""Реконструкция тредов по заголовкам RFC 5322 (Message-ID / In-Reply-To / References)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from email.utils import parseaddr

from imap_tools import MailMessage


@dataclass
class ParsedMessage:
    """Плоское представление письма для записи в БД."""

    message_id: str
    in_reply_to: str | None
    references: list[str]
    subject: str
    from_addr: str
    from_name: str | None
    to_addrs: list[str]
    cc_addrs: list[str]
    sent_at: datetime
    body_text: str


def _addr(value: tuple[str, str] | str) -> tuple[str | None, str]:
    """Нормализует '"Имя" <email>' -> (name, email)."""
    if isinstance(value, tuple):
        name, addr = value
    else:
        name, addr = parseaddr(value)
    addr = (addr or "").lower().strip()
    return (name or None, addr)


def parse_message(msg: MailMessage) -> ParsedMessage:
    """Конвертирует imap_tools MailMessage в ParsedMessage."""
    refs_raw = msg.headers.get("references", ("",))[0] if msg.headers else ""
    refs = [r for r in refs_raw.replace("\n", " ").split() if r]
    refs = [r.strip("<>") for r in refs]

    in_reply_raw = (msg.headers.get("in-reply-to", ("",))[0] if msg.headers else "") or ""
    in_reply = in_reply_raw.strip().strip("<>") or None

    _, from_addr = _addr(msg.from_values) if msg.from_values else (None, msg.from_ or "")
    from_name = msg.from_values.name if msg.from_values and msg.from_values.name else None

    to = [_addr(a)[1] for a in msg.to_values or []]
    cc = [_addr(a)[1] for a in msg.cc_values or []]

    body = (msg.text or msg.html or "").strip()

    return ParsedMessage(
        message_id=(msg.uid and msg.headers.get("message-id", (msg.uid,))[0].strip("<>"))
        or (msg.headers.get("message-id", ("",))[0].strip("<>") if msg.headers else ""),
        in_reply_to=in_reply,
        references=refs,
        subject=msg.subject or "",
        from_addr=from_addr,
        from_name=from_name,
        to_addrs=to,
        cc_addrs=cc,
        sent_at=msg.date,
        body_text=body,
    )


def find_root_message_id(pm: ParsedMessage) -> str:
    """Определяет идентификатор корневого письма треда.

    Предпочтение: первый элемент References (самый ранний предок).
    Если References пуст — сам Message-ID (мы корень).
    Если есть только In-Reply-To — берём его.
    """
    if pm.references:
        return pm.references[0]
    if pm.in_reply_to:
        return pm.in_reply_to
    return pm.message_id
