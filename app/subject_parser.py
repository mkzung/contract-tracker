"""Парсинг темы письма 'На согласование: договор с ... на ... (регион, объект)'."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.config import settings

# Примеры:
#   На согласование: договор с ООО Альфа на устройство перегородок и отделку (Москва, Объект-А)
#   На согласование: договор с ИП Иванов на устройство ростверков (Казань)
#   Re: На согласование: договор с ООО "Бета" на внеплощадочные сети (Москва, Объект-Б)
_RE_RE_PREFIX = re.compile(r"^\s*(?:Re|RE|Fwd|FW|Fw)\s*:\s*", re.IGNORECASE)
_RE_SUBJECT = re.compile(
    r"^(?P<prefix>На согласование)\s*:\s*"
    r"(?:договор|ДС|дополнительное соглашение|соглашение)\s+с\s+"
    r"(?P<contractor>.+?)\s+на\s+"
    r"(?P<matter>.+?)\s*"
    r"(?:\((?P<location>[^)]+)\))?\s*$",
    re.IGNORECASE | re.UNICODE,
)


@dataclass(frozen=True)
class SubjectInfo:
    is_approval_subject: bool
    contractor: str | None
    subject_matter: str | None
    region: str | None
    object_name: str | None


def strip_reply_prefixes(subject: str) -> str:
    """Убирает цепочку Re:/Fwd: в начале темы."""
    stripped = subject
    while True:
        new = _RE_RE_PREFIX.sub("", stripped, count=1)
        if new == stripped:
            return new.strip()
        stripped = new


def parse_subject(subject: str) -> SubjectInfo:
    """Разбирает тему рассылки 'На согласование: ...'.

    Возвращает SubjectInfo с is_approval_subject=False, если формат не распознан.
    Регион и объект разбираются из скобок (формат: 'Регион, Объект' или 'Регион').
    """
    cleaned = strip_reply_prefixes(subject or "")
    if settings.subject_prefix.lower() not in cleaned.lower():
        return SubjectInfo(False, None, None, None, None)

    m = _RE_SUBJECT.match(cleaned)
    if not m:
        return SubjectInfo(True, None, None, None, None)

    location = m.group("location")
    region, obj = None, None
    if location:
        parts = [p.strip() for p in location.split(",", maxsplit=1)]
        region = parts[0] or None
        obj = parts[1] if len(parts) > 1 else None

    return SubjectInfo(
        is_approval_subject=True,
        contractor=m.group("contractor").strip(),
        subject_matter=m.group("matter").strip(),
        region=region,
        object_name=obj,
    )
