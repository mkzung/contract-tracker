# contract-tracker

Contract-approval tracker built for a mid-size construction firm. Reads a shared mailbox over IMAP, reconstructs RFC-5322 email threads marked **"На согласование:"** ("For approval:"), classifies each reply with an LLM (approval / objection / question / correction / …), and surfaces the live state of every contract on a Streamlit dashboard.

The construction company's contract review process used to live in a long, ad-hoc email chain CC-ing 8–12 reviewers per contract. Status visibility was non-existent. This project turns that flow into structured data — without changing how reviewers work — and adds a "silent approval" timer for non-responders.


## What it does

1. **IMAP poller** (`app/imap_poller.py`) — every N minutes pulls new mail from a shared mailbox via `imap-tools`, parses headers and body, persists messages in SQLite/PostgreSQL.
2. **Thread reconstruction** (`app/thread_parser.py`) — uses `Message-ID` / `In-Reply-To` / `References` to attach each reply to its root contract email; falls back gracefully when clients break threading.
3. **Subject parser** (`app/subject_parser.py`) — extracts contractor, subject matter, region, and object name from a templated subject line via regex; tolerant to `Re:` / `Fwd:` chains.
4. **LLM classifier** (`app/llm_classifier.py`) — sends each reply to an OpenAI chat-completions endpoint with a structured system prompt, expects JSON-mode output. Categories: `approval`, `conditional`, `objection`, `question`, `correction`, `info`, `unknown`. Confidence + reason returned per reply.
5. **Approval engine** (`app/approval_engine.py`) — aggregates per-thread state from individual classifications. Supports a configurable "silent approval" timer (no answer in N business days → counted as approval).
6. **Streamlit dashboard** (`app/dashboard.py`) — live view per thread: contractor, region, object, status, count of approvals/objections, full email timeline.
7. **Backfill script** (`scripts/backfill.py --since YYYY-MM-DD`) — reprocesses historical mail without rerunning the live poller.

## Stack

- Python 3.10+
- [`imap-tools`](https://pypi.org/project/imap-tools/) — IMAP client
- SQLAlchemy 2.0 (SQLite by default; switch to Postgres via `DATABASE_URL`)
- OpenAI Python SDK — reply classification (configurable model via `OPENAI_MODEL`)
- Streamlit — dashboard
- APScheduler — periodic polling and silent-approval timers
- structlog — structured logging
- pytest + ruff — tests + linting
- systemd — production deployment

## Layout

```
contract-tracker/
├── app/
│   ├── config.py             # pydantic-settings, .env-driven
│   ├── database.py           # SQLAlchemy engine + session_scope()
│   ├── models.py             # Thread, Message, Participant, Response
│   ├── subject_parser.py     # "На согласование: ..." regex parser
│   ├── thread_parser.py      # RFC 5322 thread reconstruction
│   ├── imap_poller.py        # IMAP loop, persistence
│   ├── llm_classifier.py     # OpenAI JSON-mode classifier
│   ├── approval_engine.py    # state aggregation + silent-approval
│   ├── dashboard.py          # Streamlit UI
│   └── logging_conf.py       # structlog config
├── scripts/
│   ├── init_db.py            # create tables
│   └── backfill.py           # one-off historical reprocess
├── tests/
│   └── test_subject_parser.py
├── migrations/               # alembic (when migrating to Postgres)
├── pyproject.toml
├── .env.example
└── .gitignore
```

## Run locally

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# fill in IMAP credentials and OPENAI_API_KEY

python scripts/init_db.py

# in one terminal:
python -m app.imap_poller

# in another:
streamlit run app/dashboard.py
```

## Deploy (Ubuntu 22/24, systemd)

```bash
sudo mkdir -p /opt/contract-tracker /var/lib/contract-tracker /var/log/contract-tracker
sudo useradd -r -s /bin/false tracker
sudo chown -R tracker:tracker /opt/contract-tracker /var/lib/contract-tracker /var/log/contract-tracker

cd /opt/contract-tracker
python3.11 -m venv .venv
.venv/bin/pip install -e .

cp .env.example .env  # fill in
.venv/bin/python scripts/init_db.py

# systemd units (poller + dashboard) — see systemd/ folder; ship them under /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now contract-tracker-poller contract-tracker-dashboard
```

The dashboard listens on `:8501`. Front it with nginx + TLS in production.

## Backfill

```bash
python scripts/backfill.py --since 2026-03-20
```

## Notes

- The classifier system prompt is in Russian (the production mailbox is Russian-language) — see `app/llm_classifier.py`. Easy to swap for any other language: replace the prompt + tweak the `ResponseKind` enum.
- The subject parser assumes a templated subject line (`"На согласование: договор с {contractor} на {matter} ({region}, {object})"`). Adapt the regex in `subject_parser.py` for a different convention.
- Silent-approval thresholds (e.g. 5 business days) are configured per-organization, not per-thread; the rule lives in `approval_engine.py`.
- Schema is intentionally minimal — `Thread`, `Message`, `Participant`, `Response`. Migration to Postgres is a `DATABASE_URL` change plus running `alembic upgrade head`.

## License

MIT — see [LICENSE](./LICENSE).

## Author

Maksim Gorbuk · gorbuk.maxim@gmail.com · [github.com/mkzung](https://github.com/mkzung) · [linkedin.com/in/gorbuk](https://linkedin.com/in/gorbuk)

Built while consulting on automation for a Russian construction firm (≈120 employees) — Python + OpenAI API + n8n.
