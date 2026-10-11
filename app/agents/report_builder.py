"""Report Builder Agent — generates full narrative reports with multiple charts.

Creates multi-section reports with executive summary, key metrics,
trends, top performers, predictions, and recommendations.
"""
from __future__ import annotations

import re
from dataclasses import asdict

from langgraph.graph import END, StateGraph

from app.agents.state import AgentState
from app.charts import choose_chart
from app.tools.sql_tool import sql_query_tool, get_schema_tool
from app.tools.forecaster import forecast_timeseries

_SQL_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.S | re.I)


def _clean_sql(text: str) -> str:
    m = _SQL_FENCE.search(text)
    return (m.group(1) if m else text).strip().strip(";")


def _log(state: AgentState, action: str, detail: str = "") -> list[dict]:
    log = list(state.get("agent_log") or [])
    log.append({"agent": "report_builder", "action": action, "detail": detail})
    return log


# ---- Nodes ----

def plan_report(state: AgentState, llm) -> dict:
    """Plan the report sections and their SQL queries."""
    schema_result = get_schema_tool()
    question = state.get(
        "question", "Generate a comprehensive sales analysis report"
    )

    prompt = (
        "You are a report builder agent. Plan a comprehensive data analysis "
        "report.\nCreate 4-6 sections. For each section, specify:\n"
        "SECTION: title\n"
        "PURPOSE: what this section analyzes\n"
        "SQL: the SELECT query (single line, no markdown fences)\n"
        "CHART_TYPE: bar|line|pie|scatter|table\n"
        "---\n\n"
        "Sections should cover: overview/summary, trends, top performers, "
        "comparisons, and predictions/recommendations.\n\n"
        f"Database schema:\n{schema_result['schema_text']}\n\n"
        f"Report focus: {question}"
    )
    resp = llm.invoke(prompt)

    sections: list[dict] = []
    for block in resp.content.split("---"):
        section: dict = {}
        for line in block.strip().split("\n"):
            ls = line.strip()
            if ls.upper().startswith("SECTION:"):
                section["title"] = ls.split(":", 1)[1].strip()
            elif ls.upper().startswith("PURPOSE:"):
                section["purpose"] = ls.split(":", 1)[1].strip()
            elif ls.upper().startswith("SQL:"):
                section["sql"] = _clean_sql(ls.split(":", 1)[1])
            elif ls.upper().startswith("CHART_TYPE:"):
                section["chart_type"] = ls.split(":", 1)[1].strip().lower()
        if not section.get("sql"):
            section["sql"] = _clean_sql(block)
        if section.get("sql") and len(section.get("sql", "")) > 5:
            sections.append(section)

    return {
        "sub_tasks": sections[:6],
        "schema_info": schema_result["schema_text"],
        "agent_log": _log(
            state, "plan_report", f"{len(sections)} sections planned"
        ),
    }


def execute_sections(state: AgentState, llm) -> dict:
    """Execute SQL for each report section and generate charts."""
    sections = state.get("sub_tasks", [])
    report_sections: list[dict] = []
    charts = list(state.get("charts") or [])

    for sec in sections:
        result = sql_query_tool(sec.get("sql", ""))
        section_data: dict = {
            "title": sec.get("title", "Analysis"),
            "purpose": sec.get("purpose", ""),
            "sql": sec.get("sql", ""),
        }

        if result["success"] and result["rows"]:
            section_data["columns"] = result["columns"]
            section_data["rows"] = result["rows"][:50]
            section_data["row_count"] = result["row_count"]

            # Generate chart
            spec = choose_chart(
                sec.get("title", ""),
                result["columns"],
                result["rows"],
                override=sec.get("chart_type"),
            )
            spec_dict = asdict(spec)
            spec_dict["title"] = sec.get("title", spec_dict.get("title", ""))
            section_data["chart"] = spec_dict
            charts.append(spec_dict)

            # Auto-forecast for trend sections
            title_lower = sec.get("title", "").lower()
            if any(kw in title_lower for kw in
                   ["trend", "forecast", "predict", "monthly"]):
                date_col = value_col = None
                for i, col in enumerate(result["columns"]):
                    if any(kw in col.lower()
                           for kw in ["date", "month", "year"]):
                        date_col = col
                    else:
                        try:
                            float(result["rows"][0][i])
                            if not value_col:
                                value_col = col
                        except (ValueError, TypeError, IndexError):
                            pass
                if date_col and value_col:
                    fc = forecast_timeseries(
                        result["columns"], result["rows"],
                        date_col, value_col, periods=3,
                    )
                    if fc.get("success"):
                        section_data["forecast"] = fc
                        charts.append({
                            "type": "forecast",
                            "historical": fc["historical"],
                            "forecast": fc["forecast"],
                            "title": f"Forecast: {sec.get('title', '')}",
                            "reason": "Automated forecast for trend section",
                        })
        else:
            section_data["error"] = "; ".join(
                result.get("errors", ["Query failed"])
            )

        report_sections.append(section_data)

    return {
        "report_sections": report_sections,
        "charts": charts,
        "agent_log": _log(
            state,
            "execute_sections",
            f"{len(report_sections)} sections completed",
        ),
    }


def generate_narrative(state: AgentState, llm) -> dict:
    """Generate the full narrative report."""
    sections = state.get("report_sections", [])
    if not sections:
        return {
            "answer": "Could not generate report — no data available.",
            "agent_log": _log(state, "generate_narrative", "no sections"),
        }

    section_data = []
    for sec in sections:
        preview = ""
        if sec.get("columns") and sec.get("rows"):
            preview = str([sec["columns"]] + sec["rows"][:10])
        fc_note = ""
        if sec.get("forecast", {}).get("success"):
            fc = sec["forecast"]
            fc_note = (
                f"\nForecast: next values = {fc['forecast']['values']}, "
                f"trend = {fc['trend_direction']}"
            )
        section_data.append(
            f"## {sec.get('title', 'Section')}\n"
            f"Purpose: {sec.get('purpose', '')}\n"
            f"Data: {preview}{fc_note}"
        )

    prompt = (
        "You are a data analyst writing a professional report. Write a "
        "comprehensive narrative report based on the data below. Format with "
        "markdown headers.\n\n"
        "Include:\n"
        "1. **Executive Summary** (2-3 key takeaways)\n"
        "2. A narrative paragraph for each data section\n"
        "3. **Recommendations** (3-4 actionable items based on the data)\n\n"
        "Rules: Use ONLY the numbers provided. Indian formats (lakh, crore) "
        "are fine.\nBe specific and actionable, not generic.\n\n"
        f"Report focus: {state['question']}\n\n"
        + "\n\n".join(section_data)
    )
    resp = llm.invoke(prompt)
    return {
        "answer": resp.content,
        "explanation": resp.content,
        "agent_log": _log(state, "generate_narrative"),
    }


# ---- Graph builder ----

def build_report_builder(llm):
    g = StateGraph(AgentState)
    g.add_node("plan", lambda s: plan_report(s, llm))
    g.add_node("execute", lambda s: execute_sections(s, llm))
    g.add_node("narrate", lambda s: generate_narrative(s, llm))

    g.set_entry_point("plan")
    g.add_edge("plan", "execute")
    g.add_edge("execute", "narrate")
    g.add_edge("narrate", END)
    return g.compile()


def run_report_builder(state: AgentState, llm) -> AgentState:
    """Run the Report Builder agent and return updated state."""
    graph = build_report_builder(llm)
    return graph.invoke(state)
