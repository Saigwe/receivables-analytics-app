"""Receivables & cash analytics app over the dbt gold layer.

Run:  streamlit run app/streamlit_app.py
The warehouse path comes from AR_DUCKDB_PATH (default warehouse/receivables.duckdb).
"""
from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = os.environ.get("AR_DUCKDB_PATH", str(ROOT / "warehouse" / "receivables.duckdb"))
BUCKETS = ["current", "1-30", "31-60", "61-90", "91-120", "120+"]

st.set_page_config(page_title="Receivables & Cash", layout="wide")


@st.cache_data(ttl=600)
def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    with duckdb.connect(DB_PATH, read_only=True) as con:
        return con.execute(sql, list(params)).df()


def money(x: float) -> str:
    return f"${x / 1e6:,.2f}M" if abs(x) >= 1e6 else f"${x:,.0f}"


if not Path(DB_PATH).exists():
    st.error(f"No warehouse at {DB_PATH}. Run `make all` first.")
    st.stop()

months = query("select month_end from gold.dim_month order by month_end desc")["month_end"]
st.sidebar.title("Receivables & Cash")
month_end = st.sidebar.selectbox("Month-end", months, format_func=lambda d: d.strftime("%b %Y"))
segments = query("select distinct segment from gold.dim_customer order by 1")["segment"].tolist()
chosen = st.sidebar.multiselect("Segment", segments, default=segments)
st.sidebar.caption("Synthetic data generated for this portfolio project. All amounts in USD at month-end rates.")

tie = query("select currency_code, gl_balance, subledger_net_ar, variance, is_tied from gold.rpt_ledger_tie "
            "where month_end = ? order by 1", (month_end,))
if tie["is_tied"].all():
    st.success(f"Ties to ledger: sub-ledger net AR equals the GL control account (1200) in all "
               f"{len(tie)} currencies at {month_end:%d %b %Y}.")
else:
    st.error("Does not tie to ledger. See the Ledger tie tab.")

overview, aging, collections, ledger, health = st.tabs(
    ["Overview", "Aging", "Collections", "Ledger tie", "Pipeline health"])

with overview:
    k = query("select * from gold.rpt_ar_kpis order by month_end")
    cur = k[k["month_end"] == month_end].iloc[0]
    prev = k[k["month_end"] < month_end].tail(1)
    delta = (lambda col: None if prev.empty or pd.isna(prev.iloc[0][col]) else float(cur[col] - prev.iloc[0][col]))
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Net AR", money(cur.net_ar_usd), None if delta("net_ar_usd") is None else money(delta("net_ar_usd")))
    c2.metric("DSO (days)", "n/a" if pd.isna(cur.dso_days) else f"{cur.dso_days:.1f}",
              None if delta("dso_days") is None else f"{delta('dso_days'):+.1f}", delta_color="inverse")
    c3.metric("CEI", "n/a" if pd.isna(cur.cei_pct) else f"{cur.cei_pct:.1f}%",
              None if delta("cei_pct") is None else f"{delta('cei_pct'):+.1f} pts")
    c4.metric("Over 60 days", f"{cur.share_over_60:.1%}",
              None if delta("share_over_60") is None else f"{delta('share_over_60'):+.1%}", delta_color="inverse")
    c5.metric("Unapplied cash", money(cur.unapplied_usd))
    st.subheader("Net AR and sales by month")
    st.line_chart(k.set_index("month_end")[["net_ar_usd", "sales_usd"]])
    st.subheader("DSO and CEI")
    st.line_chart(k.set_index("month_end")[["dso_days", "cei_pct"]])

with aging:
    a = query("select segment, aging_bucket, open_invoices, customers, open_usd from gold.rpt_ar_aging "
              "where month_end = ?", (month_end,))
    a = a[a["segment"].isin(chosen)]
    pivot = (a.pivot_table(index="aging_bucket", columns="segment", values="open_usd", aggfunc="sum")
               .reindex(BUCKETS).fillna(0))
    st.subheader(f"Open AR by aging bucket at {month_end:%d %b %Y}")
    st.bar_chart(pivot)
    st.dataframe(pivot.assign(total=pivot.sum(axis=1)).style.format("${:,.0f}"), use_container_width=True)

with collections:
    w = query("select * from gold.rpt_collections_worklist order by priority_rank")
    w = w[w["segment"].isin(chosen)]
    latest = months.iloc[0]
    st.subheader(f"Collections worklist ({latest:%b %Y}, latest month-end)")
    st.caption("Ranked by money over 60 days past due, then by total overdue.")
    st.dataframe(
        w[["priority_rank", "customer_id", "customer_name", "segment", "over_60_usd", "overdue_usd", "open_usd",
           "oldest_days_past_due", "credit_limit_used", "open_disputes", "avg_days_late_6m"]].head(200),
        use_container_width=True, hide_index=True,
        column_config={
            "over_60_usd": st.column_config.NumberColumn("Over 60 (USD)", format="$%.0f"),
            "overdue_usd": st.column_config.NumberColumn("Overdue (USD)", format="$%.0f"),
            "open_usd": st.column_config.NumberColumn("Open (USD)", format="$%.0f"),
            "credit_limit_used": st.column_config.ProgressColumn("Credit limit used", min_value=0, max_value=2),
        })
    customer = st.selectbox("Drill into a customer", w["customer_id"].head(200))
    if customer:
        inv = query("select invoice_id, invoice_date, due_date, open_amount, currency_code, days_past_due, aging_bucket "
                    "from gold.fct_ar_month_end where customer_id = ? and month_end = ? order by due_date",
                    (customer, latest))
        st.dataframe(inv, use_container_width=True, hide_index=True)

with ledger:
    st.subheader(f"Sub-ledger vs GL at {month_end:%d %b %Y} (local currency)")
    st.dataframe(query("select currency_code, open_items, unapplied_cash, subledger_net_ar, gl_balance, variance, "
                       "is_tied from gold.rpt_ledger_tie where month_end = ? order by 1", (month_end,)),
                 use_container_width=True, hide_index=True)
    st.caption("Net AR = open invoices - cash received but not yet applied. GL = AR control account 1200.")

with health:
    try:
        runs = query("select * from ops.dbt_runs order by generated_at desc")
        nodes = query("select * from ops.dbt_node_runs where run_id = ? order by execution_time_s desc",
                      (runs.iloc[0]["run_id"],))
    except duckdb.CatalogException:
        st.info("No runs recorded yet. Run `python scripts/record_run.py` after `dbt build`.")
    else:
        r = runs.iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Last dbt build", f"{r.passed}/{r.nodes} passed")
        c2.metric("Failures", int(r.failed))
        c3.metric("Build time", f"{r.elapsed_s:.1f}s")
        c4.metric("Newest payment loaded", f"{r.newest_payment_loaded_at:%d %b %Y %H:%M}")
        st.subheader("Slowest nodes in the last run")
        st.dataframe(nodes[["name", "resource_type", "status", "execution_time_s"]].head(10),
                     use_container_width=True, hide_index=True)
        if len(runs) > 1:
            st.subheader("Build time by run")
            st.line_chart(runs.set_index("generated_at")[["elapsed_s"]])
