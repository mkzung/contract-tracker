"""Streamlit dashboard for the contract-approval tracker."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import select

from app.database import session_scope
from app.models import Participant, Response, ResponseKind, Thread, ThreadStatus

st.set_page_config(page_title="Контракт-трекер", layout="wide")
st.title("Контракт-трекер: согласования договоров")

STATUS_LABEL = {
    ThreadStatus.PENDING: "В работе",
    ThreadStatus.APPROVED: "Согласовано",
    ThreadStatus.APPROVED_SILENT: "Согласовано (по дедлайну)",
    ThreadStatus.OBJECTIONS: "Замечания",
    ThreadStatus.CORRECTED: "На корректировке",
    ThreadStatus.CLOSED: "Закрыт",
}
KIND_LABEL = {
    ResponseKind.APPROVAL: "согласовал",
    ResponseKind.CONDITIONAL: "согласовал с замечаниями",
    ResponseKind.OBJECTION: "замечания",
    ResponseKind.QUESTION: "вопрос",
    ResponseKind.CORRECTION: "корректировка",
    ResponseKind.INFO: "инфо",
    ResponseKind.UNKNOWN: "не определено",
}


def _thread_rows() -> pd.DataFrame:
    with session_scope() as s:
        rows = []
        threads = s.execute(select(Thread).order_by(Thread.created_at.desc())).scalars().all()
        for t in threads:
            approved = sum(
                1
                for r in t.responses
                if r.kind in {ResponseKind.APPROVAL, ResponseKind.CONDITIONAL}
            )
            objections = sum(1 for r in t.responses if r.kind == ResponseKind.OBJECTION)
            total_expected = max(
                len({m.from_addr for m in t.messages if m.message_id != t.root_message_id}),
                len(t.responses),
            )
            rows.append(
                {
                    "id": t.id,
                    "Контрагент": t.contractor or "—",
                    "Регион": t.region or "—",
                    "Объект": t.object_name or "—",
                    "Предмет": t.subject_matter or "—",
                    "Сумма": t.contract_amount or "",
                    "Статус": STATUS_LABEL.get(t.status, t.status.value),
                    "Согласовали": approved,
                    "Замечания": objections,
                    "Ответов всего": len(t.responses),
                    "Ожидалось": total_expected,
                    "Создано": t.created_at.strftime("%d.%m %H:%M") if t.created_at else "",
                }
            )
    return pd.DataFrame(rows)


def _thread_detail(thread_id: int) -> None:
    with session_scope() as s:
        t = s.get(Thread, thread_id)
        if not t:
            st.error("Тред не найден")
            return
        st.subheader(f"{t.contractor or '—'} — {t.subject_matter or ''}")
        st.caption(f"{t.region or ''} / {t.object_name or ''} | статус: {STATUS_LABEL.get(t.status)}")

        # Список ответов
        participants = {p.id: p for p in s.execute(select(Participant)).scalars()}
        resp_rows = [
            {
                "Согласовант": participants.get(r.participant_id).display_name
                or participants.get(r.participant_id).email,
                "Email": participants.get(r.participant_id).email,
                "Статус": KIND_LABEL.get(r.kind, r.kind.value),
                "Когда": r.responded_at.strftime("%d.%m %H:%M") if r.responded_at else "",
                "Цитата": (r.snippet or "")[:200],
            }
            for r in sorted(t.responses, key=lambda x: x.responded_at or "")
        ]
        st.dataframe(pd.DataFrame(resp_rows), width="stretch", hide_index=True)

        # Timeline писем
        st.markdown("**Хронология писем:**")
        for m in t.messages:
            with st.expander(
                f"{m.sent_at.strftime('%d.%m %H:%M')} — {m.from_name or m.from_addr} "
                f"[{KIND_LABEL.get(m.classification, '—')}]"
            ):
                st.code((m.body_text or "")[:2000])


def main() -> None:
    df = _thread_rows()

    # Empty-state: без тредов нет смысла рисовать фильтры (ломались KeyError).
    if df.empty:
        st.info(
            "Пока не пришло ни одного письма «На согласование:». "
            "As soon as the project assistant adds `tracker@example.com` to CC — "
            "poller (цикл 5 мин) подхватит тред и он появится тут."
        )
        with st.expander("Состояние сервиса"):
            from app.config import settings
            st.write({
                "IMAP": f"{settings.imap_user}@{settings.imap_host}:{settings.imap_port}",
                "Папка": settings.imap_folder,
                "Интервал опроса, сек": settings.imap_poll_interval_seconds,
                "LLM модель": settings.openai_model,
            })
        return

    col_f1, col_f2, col_f3 = st.columns([1, 1, 2])
    with col_f1:
        status_filter = st.multiselect(
            "Статус", sorted(df["Статус"].unique()), default=list(df["Статус"].unique())
        )
    with col_f2:
        region_filter = st.multiselect(
            "Регион", sorted(df["Регион"].unique()), default=list(df["Регион"].unique())
        )
    with col_f3:
        search = st.text_input("Поиск по контрагенту / предмету", "")

    mask = df["Статус"].isin(status_filter) & df["Регион"].isin(region_filter)
    if search:
        s = search.lower()
        mask &= df.apply(
            lambda r: s in str(r["Контрагент"]).lower() or s in str(r["Предмет"]).lower(), axis=1
        )

    st.dataframe(df[mask].drop(columns=["id"]), width="stretch", hide_index=True)

    st.divider()
    options = df[mask][["id", "Контрагент", "Объект"]].apply(
        lambda r: f"#{r['id']} — {r['Контрагент']} / {r['Объект']}", axis=1
    ).tolist()
    ids = df[mask]["id"].tolist()
    if options:
        picked = st.selectbox("Открыть тред", options)
        if picked:
            thread_id = ids[options.index(picked)]
            _thread_detail(thread_id)


if __name__ == "__main__":
    main()
