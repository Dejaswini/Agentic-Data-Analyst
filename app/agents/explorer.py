"""Explorer Agent — autonomous data exploration and insight discovery.

Scans the database, runs multiple queries, detects anomalies and patterns,
and returns a ranked list of discoveries with auto-generated charts.
"""
from __future__ import annotations

import re
from dataclasses import asdict

from langgraph.graph import END, StateGraph

from app.agents.state import AgentState
from app.charts import choose_chart
from app.tools.sql_tool import sql_query_tool, get_schema_tool
from app.tools.anomaly_detector import detect_outliers

_SQL_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.S | re.I)


def _clean_sql(text: str) -> str:
    m = _SQL_FENCE.search(text)
    return (m.group(1) if m else text).strip().strip(";")


def _log(state: AgentState, action: str, detail: str = "") -> list[dict]:
    log = list(state.get("agent_log") or [])
    log.append({"agent": "explorer", "action": action, "detail": detail})
    return log


# ---- Nodes ----

def plan_exploration(state: AgentState, llm) -> dict:
    """Generate a set of exploration queries to discover patterns."""
    schema_result = get_schema_tool()
    question = state.get(
        "question", "Explore the data and find interesting patterns"
    )

    prompt = (
        "You are a data explorer agent. Generate 5-7 SQL queries to discover "
        "interesting patterns, anomalies, and insights in this database.\n"
        "Focus on: top performers, trends over time, unusual patterns, "
        "comparisons between groups, and distribution analysis.\n\n"
        "For each query, output exactly:\n"
        "TITLE: short description\n"
        "SQL: the SELECT query (single line, no markdown fences)\n"
        "---\n\n"
        f"Database schema:\n{schema_result['schema_text']}\n\n"
        f"Focus area: {question}"
    )
    resp = llm.invoke(prompt)

    queries: list[dict] = []
    blocks = resp.content.split("---")
    for block in blocks:
        title = ""
        sql = ""
        for line in block.strip().split("\n"):
            if line.strip().upper().startswith("TITLE:"):
                title = line.split(":", 1)[1].strip()
            elif line.strip().upper().startswith("SQL:"):
                sql = _clean_sql(line.split(":", 1)[1])
        if not sql:
            sql = _clean_sql(block)
        if sql and len(sql) > 5:
            queries.append({"title": title or "Exploration query", "sql": sql})

    return {
        "sub_tasks": queries[:7],
        "schema_info": schema_result["schema_text"],
        "agent_log": _log(
            state, "plan_exploration", f"{len(queries)} queries planned"
        ),
    }


def run_explorations(state: AgentState, llm) -> dict:
    """Execute all exploration queries and collect results."""
    queries = state.get("sub_tasks", [])
    discoveries: list[dict] = []
    charts = list(state.get("charts") or [])

    for q in queries:
        result = sql_query_tool(q["sql"])
        if not result["success"] or not result["rows"]:
            continue

        discovery: dict = {
            "title": q["title"],
            "sql": q["sql"],
            "columns": result["columns"],
            "rows": result["rows"][:20],
            "row_count": result["row_count"],
        }

        # Try anomaly detection on the first numeric column
        for i, col in enumerate(result["columns"]):
            try:
                float(result["rows"][0][i])
                outlier_result = detect_outliers(
                    result["columns"], result["rows"], col
                )
                if (
                    outlier_result.get("success")
                    and outlier_result.get("outlier_count", 0) > 0
                ):
                    discovery["anomalies"] = outlier_result
                break
            except (ValueError, TypeError, IndexError):
                continue

        # Auto-generate chart
        spec = choose_chart(q["title"], result["columns"], result["rows"])
        if spec.type != "table":
            discovery["chart"] = asdict(spec)
            charts.append(asdict(spec))

        discoveries.append(discovery)

    return {
        "discoveries": discoveries,
        "charts": charts,
        "agent_log": _log(
            state, "run_explorations", f"{len(discoveries)} discoveries"
        ),
    }


def rank_and_narrate(state: AgentState, llm) -> dict:
    """Rank discoveries by interestingness and generate narrative."""
    discoveries = state.get("discoveries", [])
    if not discoveries:
        return {
            "answer": (
                "I explored the database but didn't find enough data to "
                "generate insights."
            ),
            "explanation": "No significant patterns found.",
            "agent_log": _log(state, "rank_and_narrate", "no discoveries"),
        }

    summaries = []
    for i, d in enumerate(discoveries, 1):
        preview = [d["columns"]] + d["rows"][:5]
        anomaly_note = ""
        if d.get("anomalies", {}).get("outlier_count", 0) > 0:
            anomaly_note = (
                f" [⚠️ {d['anomalies']['outlier_count']} outliers detected]"
            )
        summaries.append(
            f"{i}. {d['title']}{anomaly_note}\n   Data: {preview}"
        )

    prompt = (
        "You are a data explorer presenting your findings. Rank these "
        "discoveries by how interesting/actionable they are. Present the top "
        "findings with:\n"
        "- A 🔍 emoji for each finding\n"
        "- Clear, concise explanation using ONLY the numbers shown\n"
        "- Flag any anomalies with ⚠️\n"
        "- Suggest follow-up questions the user might want to ask\n\n"
        "Discoveries:\n" + "\n".join(summaries)
    )
    resp = llm.invoke(prompt)
    return {
        "answer": resp.content,
        "explanation": resp.content,
        "agent_log": _log(state, "rank_and_narrate"),
    }


# ---- Graph builder ----

def build_explorer(llm):
    g = StateGraph(AgentState)
    g.add_node("plan", lambda s: plan_exploration(s, llm))
    g.add_node("explore", lambda s: run_explorations(s, llm))
    g.add_node("narrate", lambda s: rank_and_narrate(s, llm))

    g.set_entry_point("plan")
    g.add_edge("plan", "explore")
    g.add_edge("explore", "narrate")
    g.add_edge("narrate", END)
    return g.compile()


def run_explorer(state: AgentState, llm) -> AgentState:
    """Run the Explorer agent and return updated state."""
    graph = build_explorer(llm)
    return graph.invoke(state)
