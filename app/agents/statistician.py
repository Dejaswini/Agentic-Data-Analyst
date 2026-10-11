"""Statistician Agent — statistical analysis, forecasting, anomaly detection.

Flow: plan_analysis → fetch_data → run_statistics → interpret → END
"""
from __future__ import annotations

import re
from typing import Any

from langgraph.graph import END, StateGraph

from app.agents.state import AgentState
from app.tools.sql_tool import sql_query_tool, get_schema_tool
from app.tools.stats_engine import (
    summary_statistics,
    growth_rates,
    detect_seasonality,
)
from app.tools.forecaster import forecast_timeseries
from app.tools.anomaly_detector import detect_outliers, detect_spikes

_SQL_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.S | re.I)


def _clean_sql(text: str) -> str:
    m = _SQL_FENCE.search(text)
    return (m.group(1) if m else text).strip().strip(";")


def _log(state: AgentState, action: str, detail: str = "") -> list[dict]:
    log = list(state.get("agent_log") or [])
    log.append({"agent": "statistician", "action": action, "detail": detail})
    return log


# ---- Nodes ----

def plan_analysis(state: AgentState, llm) -> dict:
    """Decide which statistical tools to apply and write a data-fetch SQL."""
    schema_result = get_schema_tool()
    prompt = (
        "You are a statistician agent. Given the user's question, plan what "
        "analysis to do.\n"
        "Available analyses: summary_statistics, growth_rates, seasonality, "
        "forecast, outliers, spikes.\n"
        "Also write ONE SQL query to fetch the data needed (time series "
        "preferred: date + value columns).\n\n"
        "Output format (exactly):\n"
        "ANALYSES: comma-separated list\n"
        "SQL: the query\n"
        "VALUE_COL: the numeric column name\n"
        "DATE_COL: the date column name (or 'none')\n\n"
        f"Database schema:\n{schema_result['schema_text']}\n\n"
        f"Question: {state['question']}"
    )
    resp = llm.invoke(prompt)
    text = resp.content

    analyses: list[str] = []
    sql = ""
    value_col = ""
    date_col = ""
    for line in text.split("\n"):
        ls = line.strip()
        if ls.upper().startswith("ANALYSES:"):
            analyses = [a.strip().lower() for a in ls.split(":", 1)[1].split(",")]
        elif ls.upper().startswith("SQL:"):
            sql = _clean_sql(ls.split(":", 1)[1])
        elif ls.upper().startswith("VALUE_COL:"):
            value_col = ls.split(":", 1)[1].strip()
        elif ls.upper().startswith("DATE_COL:"):
            date_col = ls.split(":", 1)[1].strip()

    if not sql:
        sql = _clean_sql(text)

    return {
        "sql": sql,
        "schema_info": schema_result["schema_text"],
        "stats_results": {
            "planned_analyses": analyses,
            "value_col": value_col,
            "date_col": date_col,
        },
        "agent_log": _log(
            state, "plan_analysis", f"analyses={analyses}, sql={sql[:80]}"
        ),
    }


def fetch_data(state: AgentState, llm) -> dict:
    """Execute the SQL to get data for analysis."""
    result = sql_query_tool(state["sql"])
    if not result["success"]:
        return {
            "execution_error": "; ".join(result.get("errors", [])),
            "agent_log": _log(
                state, "fetch_data_failed", str(result["errors"])
            ),
        }
    return {
        "columns": result["columns"],
        "rows": result["rows"],
        "execution_error": "",
        "agent_log": _log(state, "fetch_data", f"{result['row_count']} rows"),
    }


def run_statistics(state: AgentState, llm) -> dict:
    """Run the planned statistical analyses on the fetched data."""
    stats = dict(state.get("stats_results") or {})
    planned = stats.get("planned_analyses", [])
    value_col: str = stats.get("value_col", "")
    date_col: str = stats.get("date_col", "")
    columns = state.get("columns", [])
    rows = state.get("rows", [])
    charts = list(state.get("charts") or [])

    if not columns or not rows:
        return {
            "stats_results": {**stats, "error": "No data to analyze"},
            "agent_log": _log(state, "run_statistics", "no data"),
        }

    # Auto-detect columns if not specified or missing
    if not value_col or value_col not in columns:
        for i, col in enumerate(columns):
            try:
                float(rows[0][i])
                value_col = col
                break
            except (ValueError, TypeError, IndexError):
                continue
    if not date_col or date_col == "none" or date_col not in columns:
        date_col = ""
        for col in columns:
            if any(
                kw in col.lower()
                for kw in ["date", "month", "year", "time", "period"]
            ):
                date_col = col
                break

    results: dict[str, Any] = {"value_col": value_col, "date_col": date_col}

    if "summary_statistics" in planned and value_col:
        results["summary"] = summary_statistics(columns, rows, value_col)

    if "growth_rates" in planned and value_col and date_col:
        results["growth"] = growth_rates(columns, rows, date_col, value_col)

    if "seasonality" in planned and value_col and date_col:
        results["seasonality"] = detect_seasonality(
            columns, rows, date_col, value_col
        )

    if "forecast" in planned and value_col and date_col:
        fc = forecast_timeseries(columns, rows, date_col, value_col, periods=6)
        results["forecast"] = fc
        if fc.get("success"):
            charts.append({
                "type": "forecast",
                "historical": fc["historical"],
                "forecast": fc["forecast"],
                "title": f"Forecast: {state['question'].strip().rstrip('?')}",
                "reason": f"Time series forecast ({fc['method']})",
            })

    if "outliers" in planned and value_col:
        results["outliers"] = detect_outliers(columns, rows, value_col)

    if "spikes" in planned and value_col and date_col:
        results["spikes"] = detect_spikes(
            columns, rows, date_col, value_col
        )

    ran = len([k for k in results if k not in ("value_col", "date_col")])
    return {
        "stats_results": results,
        "charts": charts,
        "agent_log": _log(state, "run_statistics", f"ran {ran} analyses"),
    }


def interpret(state: AgentState, llm) -> dict:
    """Human-readable interpretation of the statistical results."""
    stats = state.get("stats_results", {})
    preview = [state.get("columns", [])] + (state.get("rows", [])[:10])
    prompt = (
        "You are a statistician explaining analysis results in plain language.\n"
        "Use ONLY the numbers provided. Indian formats (lakh, crore) are fine.\n"
        "Highlight key findings: trends, anomalies, forecasts, seasonal "
        "patterns.\nBe concise but insightful (3-6 sentences).\n\n"
        f"Question: {state['question']}\n"
        f"Data preview:\n{preview}\n\n"
        f"Statistical results:\n{stats}\n"
    )
    resp = llm.invoke(prompt)
    return {
        "explanation": resp.content,
        "answer": resp.content,
        "agent_log": _log(state, "interpret"),
    }


def interpret_error(state: AgentState, llm) -> dict:
    err = state.get("execution_error", "unknown error")
    return {"answer": f"Could not fetch data for analysis: {err}", "explanation": err}


# ---- Routing ----

def _after_fetch(state: AgentState) -> str:
    return (
        "run_statistics" if not state.get("execution_error") else "interpret_error"
    )


# ---- Graph builder ----

def build_statistician(llm):
    g = StateGraph(AgentState)
    g.add_node("plan_analysis", lambda s: plan_analysis(s, llm))
    g.add_node("fetch_data", lambda s: fetch_data(s, llm))
    g.add_node("run_statistics", lambda s: run_statistics(s, llm))
    g.add_node("interpret", lambda s: interpret(s, llm))
    g.add_node("interpret_error", lambda s: interpret_error(s, llm))

    g.set_entry_point("plan_analysis")
    g.add_edge("plan_analysis", "fetch_data")
    g.add_conditional_edges(
        "fetch_data",
        _after_fetch,
        {"run_statistics": "run_statistics", "interpret_error": "interpret_error"},
    )
    g.add_edge("run_statistics", "interpret")
    g.add_edge("interpret", END)
    g.add_edge("interpret_error", END)
    return g.compile()


def run_statistician(state: AgentState, llm) -> AgentState:
    """Run the Statistician agent and return updated state."""
    graph = build_statistician(llm)
    return graph.invoke(state)
