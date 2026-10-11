"""Streamlit UI for the Multi-Agent Data Analyst.

Run:  streamlit run ui/streamlit_app.py
(Talks to the FastAPI backend; override with API_URL in .env.)
"""
from __future__ import annotations

import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
API_URL = os.environ.get("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Agentic Data Analyst",
    page_icon="🧠",
    layout="wide",
)

# ---- Custom CSS ----
st.markdown(
    """
<style>
/* Agent badges */
.agent-badge {
    display: inline-block; padding: 3px 12px; border-radius: 14px;
    font-size: 0.78em; font-weight: 600; margin-right: 6px;
    letter-spacing: 0.02em;
}
.badge-query        { background: #e3f2fd; color: #1565c0; }
.badge-statistical  { background: #f3e5f5; color: #7b1fa2; }
.badge-exploration  { background: #e8f5e9; color: #2e7d32; }
.badge-goal         { background: #fff3e0; color: #e65100; }
.badge-report       { background: #fce4ec; color: #c62828; }
.badge-chat         { background: #e0f2f1; color: #00695c; }
/* Log entry */
.log-entry { font-size: 0.85em; padding: 2px 0; }
</style>
""",
    unsafe_allow_html=True,
)

st.title("🧠 Agentic Data Analyst")
st.caption(
    "Multi-agent system — SQL Expert · Statistician · Explorer · Report Builder"
)

# ---- Session state ----
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None
if "turns" not in st.session_state:
    st.session_state.turns = []


# ---- Helpers ----

_BADGE_LABELS = {
    "query": "🔍 SQL Expert",
    "statistical": "📊 Statistician",
    "exploration": "🔭 Explorer",
    "goal": "🎯 Goal Analysis",
    "report": "📝 Report",
    "chat": "💬 Chat",
}

_AGENT_ICONS = {
    "orchestrator": "🧠",
    "sql_expert": "🔍",
    "statistician": "📊",
    "explorer": "🔭",
    "report_builder": "📝",
}


def _badge_html(task_type: str) -> str:
    label = _BADGE_LABELS.get(task_type, task_type)
    return f'<span class="agent-badge badge-{task_type}">{label}</span>'


def render_chart(chart: dict, df: pd.DataFrame | None = None) -> None:
    """Render a single chart (bar, line, pie, scatter, forecast, or table)."""
    ctype = chart.get("type", "table")

    # ---- Forecast chart with confidence band ----
    if ctype == "forecast" and chart.get("historical") and chart.get("forecast"):
        hist = chart["historical"]
        fc = chart["forecast"]
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=hist["dates"],
                y=hist["values"],
                mode="lines+markers",
                name="Historical",
                line=dict(color="#1976d2", width=2),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=fc["dates"],
                y=fc["values"],
                mode="lines+markers",
                name="Forecast",
                line=dict(color="#e65100", width=2, dash="dash"),
            )
        )
        if fc.get("upper_ci") and fc.get("lower_ci"):
            fig.add_trace(
                go.Scatter(
                    x=fc["dates"] + fc["dates"][::-1],
                    y=fc["upper_ci"] + fc["lower_ci"][::-1],
                    fill="toself",
                    fillcolor="rgba(230,81,0,0.12)",
                    line=dict(color="rgba(255,255,255,0)"),
                    name="95% Confidence",
                )
            )
        fig.update_layout(
            title=chart.get("title", "Forecast"),
            template="plotly_white",
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)
        return

    # ---- Standard charts (need df + x + y) ----
    if ctype == "table" or not chart.get("x") or not chart.get("y"):
        return
    if df is None:
        return
    x, y, title = chart["x"], chart["y"], chart.get("title", "")
    if x not in df.columns or y not in df.columns:
        return

    chart_fn = {
        "bar": lambda: px.bar(df, x=x, y=y, title=title),
        "line": lambda: px.line(df, x=x, y=y, title=title, markers=True),
        "pie": lambda: px.pie(df, names=x, values=y, title=title),
        "scatter": lambda: px.scatter(df, x=x, y=y, title=title),
    }
    if ctype in chart_fn:
        st.plotly_chart(chart_fn[ctype](), use_container_width=True)
    if chart.get("reason"):
        st.caption(f"Chart: {chart['reason']}")


def render_result(turn: dict) -> None:
    """Render one assistant turn (all response data)."""
    resp = turn["response"]
    task_type = resp.get("task_type", "query")

    # --- Badge ---
    st.markdown(_badge_html(task_type), unsafe_allow_html=True)

    # --- SQL expander ---
    if resp.get("sql"):
        retry_note = (
            f" (self-corrected {resp['retries']}×)" if resp.get("retries") else ""
        )
        with st.expander(f"Generated SQL{retry_note}"):
            st.code(resp["sql"], language="sql")

    # --- Data table ---
    df = None
    if resp.get("rows") and resp.get("columns"):
        df = pd.DataFrame(resp["rows"], columns=resp["columns"])

    # --- Charts ---
    charts = resp.get("charts") or []
    for chart in charts:
        render_chart(chart, df)

    # --- Data table expander ---
    if df is not None:
        with st.expander("Result table"):
            st.dataframe(df, use_container_width=True)

    # --- Statistical results ---
    stats = resp.get("stats_results") or {}
    has_stats = any(
        k not in ("value_col", "date_col", "planned_analyses") for k in stats
    )
    if stats and has_stats:
        with st.expander("📊 Statistical Analysis"):
            if stats.get("summary", {}).get("success"):
                s = stats["summary"]
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Mean", f"₹{s['mean']:,.2f}")
                c2.metric("Median", f"₹{s['median']:,.2f}")
                c3.metric("Std Dev", f"₹{s['std']:,.2f}")
                c4.metric("Range", f"₹{s['min']:,.2f} – ₹{s['max']:,.2f}")
            if stats.get("growth", {}).get("success"):
                st.markdown(
                    f"**Avg growth rate:** {stats['growth']['avg_growth_pct']}%"
                )
            if stats.get("seasonality", {}).get("success"):
                sea = stats["seasonality"]
                st.markdown(
                    f"**Peak month:** {sea['peak_month']} · "
                    f"**Lowest month:** {sea['trough_month']} · "
                    f"**Seasonality strength:** {sea['seasonality_strength']}"
                )
            if stats.get("forecast", {}).get("success"):
                fc = stats["forecast"]
                st.markdown(
                    f"**Trend:** {fc['trend_direction']} "
                    f"(slope: {fc['trend_slope']})"
                )
            if stats.get("outliers", {}).get("success"):
                o = stats["outliers"]
                st.markdown(
                    f"**Outliers:** {o['outlier_count']}/{o['total_count']} "
                    f"({o['outlier_pct']}%)"
                )
            if stats.get("spikes", {}).get("success"):
                st.markdown(
                    f"**Spikes/drops detected:** "
                    f"{stats['spikes']['spike_count']}"
                )

    # --- Discoveries (Explorer) ---
    discoveries = resp.get("discoveries") or []
    if discoveries and task_type == "exploration":
        with st.expander("🔭 Discoveries", expanded=True):
            for i, d in enumerate(discoveries, 1):
                st.markdown(f"**{i}. {d.get('title', 'Finding')}**")
                if d.get("columns") and d.get("rows"):
                    ddf = pd.DataFrame(
                        d["rows"][:10], columns=d["columns"]
                    )
                    st.dataframe(ddf, use_container_width=True)
                if d.get("anomalies", {}).get("outlier_count", 0) > 0:
                    st.warning(
                        f"⚠️ {d['anomalies']['outlier_count']} outliers "
                        "detected"
                    )
                st.divider()

    # --- Report sections ---
    sections = resp.get("report_sections") or []
    if sections:
        with st.expander("📝 Report Sections", expanded=True):
            for sec in sections:
                st.subheader(sec.get("title", "Section"))
                if sec.get("columns") and sec.get("rows"):
                    sdf = pd.DataFrame(
                        sec["rows"][:20], columns=sec["columns"]
                    )
                    if sec.get("chart"):
                        render_chart(sec["chart"], sdf)
                    with st.expander("Section data"):
                        st.dataframe(sdf, use_container_width=True)
                st.divider()

    # --- Answer text ---
    st.markdown(resp.get("answer", ""))

    # --- Agent activity log ---
    agent_log = resp.get("agent_log") or []
    if agent_log:
        with st.expander("🔧 Agent activity log"):
            for entry in agent_log:
                agent = entry.get("agent", "?")
                action = entry.get("action", "?")
                detail = entry.get("detail", "")
                icon = _AGENT_ICONS.get(agent, "⚙️")
                line = f"{icon} **{agent}** → {action}"
                if detail:
                    line += f": `{detail[:120]}`"
                st.markdown(line)


# ---- Chat history ----
for turn in st.session_state.turns:
    with st.chat_message("user"):
        st.markdown(turn["question"])
    with st.chat_message("assistant"):
        render_result(turn)

# ---- Chat input ----
question = st.chat_input(
    "Ask anything — data questions, forecasts, exploration, or a full report…"
)
if question:
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner(
            "🧠 Multi-agent system working "
            "(classify → route → analyze → respond)…"
        ):
            try:
                r = requests.post(
                    f"{API_URL}/ask",
                    json={
                        "question": question,
                        "conversation_id": st.session_state.conversation_id,
                    },
                    timeout=180,
                )
                r.raise_for_status()
                resp = r.json()
            except Exception as exc:
                st.error(f"Backend error: {exc}")
                st.stop()
        st.session_state.conversation_id = resp["conversation_id"]
        st.session_state.turns.append(
            {"question": question, "response": resp}
        )
        st.rerun()

# ---- Sidebar ----
with st.sidebar:
    st.header("🧠 Multi-Agent System")
    st.markdown(
        """
**Agents are activated automatically based on your question:**

| Agent | Trigger |
|-------|---------|
| 🔍 SQL Expert | Data questions |
| 📊 Statistician | Forecasts, trends |
| 🔭 Explorer | "Explore", "patterns" |
| 🎯 Goal Analyst | "Help me…", "Why…" |
| 📝 Report Builder | "Report", "overview" |
"""
    )

    st.divider()
    st.header("Try these")

    _EXAMPLES = {
        "🔍 Query": [
            "Which product generated the highest revenue?",
            "What were the total sales in Tamil Nadu last year?",
        ],
        "📊 Statistical": [
            "Forecast monthly sales for the next 6 months",
            "What is the growth rate of revenue over time?",
        ],
        "🔭 Exploration": [
            "Explore the data and find interesting patterns",
            "Any anomalies or unusual patterns in the sales?",
        ],
        "🎯 Goal": [
            "Help me increase revenue in Kerala",
            "Why are wholesale sales declining?",
        ],
        "📝 Report": [
            "Generate a comprehensive sales performance report",
            "Give me an overview of Q3 2025 performance",
        ],
    }
    for category, questions in _EXAMPLES.items():
        st.markdown(f"**{category}**")
        for q in questions:
            st.markdown(f"- {q}")

    st.divider()
    if st.button("🔄 New conversation"):
        st.session_state.conversation_id = None
        st.session_state.turns = []
        st.rerun()
