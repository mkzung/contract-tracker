"""One-off backfill: разбирает историю ящика за период и заливает в БД."""

from __future__ import annotations

import argparse
from datetime import datetime

from app.approval_engine import tick
from app.imap_poller import process_new_messages
from app.logging_conf import configure_logging, get_logger


def main() -> None:
    configure_logging()
    log = get_logger(__name__)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--since",
        type=str,
        required=True,
        help="Дата в формате YYYY-MM-DD. Пример: --since 2026-03-20",
    )
    parser.add_argument("--limit", type=int, default=None, help="Лимит писем на проход")
    args = parser.parse_args()

    since = datetime.strptime(args.since, "%Y-%m-%d")
    log.info("backfill.start", since=since.isoformat())
    n = process_new_messages(since=since, limit=args.limit)
    log.info("backfill.imap_done", imported=n)

    log.info("backfill.classify_start")
    tick()
    log.info("backfill.done")


if __name__ == "__main__":
    main()
