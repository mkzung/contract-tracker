"""Классификация ответов согласовантов через OpenAI API (gpt-5.4)."""

from __future__ import annotations

import json
from dataclasses import dataclass

from openai import OpenAI

from app.config import settings
from app.logging_conf import get_logger
from app.models import ResponseKind

log = get_logger(__name__)

_client = OpenAI(api_key=settings.openai_api_key)

_SYSTEM_PROMPT = """Ты — классификатор ответов по согласованию договоров в русской строительной компании.
На вход получаешь контекст (тема письма, отправитель) и текст ответа. Возвращаешь СТРОГО JSON с полями:
{
  "classification": "approval" | "conditional" | "objection" | "question" | "correction" | "info" | "unknown",
  "confidence": 0.0 — 1.0,
  "reason": "короткое объяснение на русском"
}

Правила:
- "approval" — явное согласование: "согласовано", "ок", "все норм", "без замечаний", "да, подписываем".
- "conditional" — согласование с мелкими замечаниями: "в остальном согласовано, поправьте сумму/НДС".
- "objection" — содержательные замечания блокируют договор: "стоимость неверно", "ТЗ изменилось", "исправьте".
- "question" — уточняющий вопрос без позиции: "почему тогда ...", "а что с ...".
- "correction" — отправитель ПРИСЛАЛ исправленную версию: "Сумму исправила. Срок возврата на 181 день" (это сам инициатор правит после замечаний, новый круг согласований).
- "info" — информационное сообщение, не относящееся к согласованию ("для информации", пересылки).
- "unknown" — не удалось классифицировать.
"""


@dataclass
class Classification:
    kind: ResponseKind
    confidence: float
    reason: str


def classify(
    *, subject: str, from_name: str | None, from_addr: str, body_text: str
) -> Classification:
    """Классифицирует один ответ. Один вызов OpenAI API."""
    snippet = (body_text or "").strip()[:1500]
    user_msg = (
        f"Тема: {subject}\n"
        f"Отправитель: {from_name or ''} <{from_addr}>\n"
        f"Текст ответа:\n{snippet}\n"
    )

    resp = _client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
        # NB: reasoning-модели gpt-5.* не принимают max_tokens/temperature напрямую —
        # опускаем оба параметра, чтобы работало с обычными и reasoning-моделями.
    )

    raw = (resp.choices[0].message.content or "").strip()

    try:
        # С response_format=json_object ответ уже валидный JSON, но оставим защиту.
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            payload = json.loads(raw[start : end + 1])
        else:
            payload = {}
        kind = ResponseKind(payload.get("classification", "unknown"))
        conf = float(payload.get("confidence", 0.0))
        reason = str(payload.get("reason", ""))[:500]
    except (ValueError, json.JSONDecodeError) as exc:
        log.warning("classifier.parse_error", raw=raw, error=str(exc))
        return Classification(ResponseKind.UNKNOWN, 0.0, f"parse error: {exc}")

    return Classification(kind, conf, reason)
