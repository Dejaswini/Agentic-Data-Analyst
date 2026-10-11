"""SQL Expert Agent — schema-aware SQL generation with self-correction.

Enhanced version of the original single agent, now usable as a sub-agent
within the multi-agent orchestrator.
"""
from __future__ import annotations

import re
from dataclasses import asdict

from langgraph.graph import END, StateGraph

from app.agents.state import AgentState
from app.charts import choose_chart
from app.config import settings
from app.tools.sql_tool import sql_query_tool, get_schema_tool

_SQL_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.S | re.I)


def _clean_sql(text: str) -> str:
    m = _SQL_FENCE.search(text)
    sql = m.group(1) if m else text
    return sql.strip().strip(";")


def _log(state: AgentState, action: str, detail: str = "") -> list[dict]:
    log = list(state.get("agent_log") or [])
    log.append({"agent": "sql_expert", "action": action, "detail": detail})
    return log


# ---- Nodes ----

def understand(state: AgentState, llm) -> dict:
    history = "\n".join(
        f"Q: {h['question']}\nA: {h['answer']}"
        for h in state.get("history", [])[-4:]
    )
    prompt = (
        "You are part of a data analyst agent. Summarise what the user wants "
        "in one or two short sentences: the metric, the grouping, any filters "
        "(place, date range), and the desired output. Resolve follow-up "
        "references ('it', 'that', 'show as chart') using the conversation.\n\n"
        f"Conversation so far:\n{history or '(none)'}\n\n"
        f"New question: {state['question']}"
    )
    resp = llm.invoke(prompt)
    return {
        "intent": resp.content,
        "agent_log": _log(state, "understand", resp.content),
    }


def fetch_schema(state: AgentState, llm) -> dict:
    result = get_schema_tool()
    return {
        "schema_info": result["schema_text"],
        "agent_log": _log(state, "fetch_schema"),
    }


def generate_sql(state: AgentState, llm) -> dict:
    prompt = (
        "You are a PostgreSQL expert. Write ONE read-only SELECT query that "
        "answers the question. Rules:\n"
        "- Output ONLY the SQL, no explanation, no markdown fences.\n"
        "- Use only the tables and columns listed below.\n"
        "- Always alias computed columns clearly (e.g. AS total_sales).\n"
        "- For 'top N' use ORDER BY ... DESC LIMIT n.\n"
        "- For monthly trends use date_trunc('month', sale_date).\n"
        "- 'last year' means the previous calendar year.\n\n"
        f"{state['schema_info']}\n\n"
        f"What the user wants: {state['intent']}\n"
        f"Original question: {state['question']}"
    )
    resp = llm.invoke(prompt)
    sql = _clean_sql(resp.content)
    return {"sql": sql, "agent_log": _log(state, "generate_sql", sql)}


def validate_and_execute(state: AgentState, llm) -> dict:
    result = sql_query_tool(state["sql"])
    if result["success"]:
        return {
            "columns": result["columns"],
            "rows": result["rows"],
            "execution_error": "",
            "validation_errors": [],
            "agent_log": _log(
                state, "execute", f"{result['row_count']} rows returned"
            ),
        }
    return {
        "execution_error": "; ".join(result.get("errors", ["Unknown error"])),
        "agent_log": _log(state, "execute_failed", str(result["errors"])),
    }


def correct_sql(state: AgentState, llm) -> dict:
    problem = state.get("execution_error") or "; ".join(
        state.get("validation_errors", [])
    )
    prompt = (
        "A PostgreSQL SELECT query failed. Fix it. Output ONLY the corrected "
        "SQL, no explanation, no markdown fences.\n\n"
        f"Schema:\n{state['schema_info']}\n\n"
        f"Question: {state['question']}\n"
        f"Broken SQL:\n{state['sql']}\n\n"
        f"Error:\n{problem}"
    )
    resp = llm.invoke(prompt)
    sql = _clean_sql(resp.content)
    return {
        "sql": sql,
        "retries": state.get("retries", 0) + 1,
        "execution_error": "",
        "validation_errors": [],
        "agent_log": _log(
            state,
            "correct_sql",
            f"retry {state.get('retries', 0) + 1}: {sql}",
        ),
    }


def analyze(state: AgentState, llm) -> dict:
    preview = [state["columns"]] + state["rows"][:20]
    prompt = (
        "You are a data analyst explaining a result in simple language. "
        "Use ONLY the numbers below — never invent values. Indian formats "
        "like lakh are fine. 2-4 sentences. If the result is empty, say so "
        "plainly.\n\n"
        f"Question: {state['question']}\n"
        f"SQL used: {state['sql']}\n"
        f"Result (header + first rows):\n{preview}"
    )
    resp = llm.invoke(prompt)
    return {
        "explanation": resp.content,
        "answer": resp.content,
        "agent_log": _log(state, "analyze"),
    }


def visualize(state: AgentState, llm) -> dict:
    spec = choose_chart(
        state["question"],
        state.get("columns", []),
        state.get("rows", []),
    )
    charts = list(state.get("charts") or [])
    charts.append(asdict(spec))
    return {"charts": charts, "agent_log": _log(state, "visualize", spec.type)}


def failed(state: AgentState, llm) -> dict:
    problem = state.get("execution_error") or "; ".join(
        state.get("validation_errors", [])
    )
    answer = (
        "I could not get a correct query after "
        f"{settings.max_sql_retries} attempts. Last error: {problem}. "
        "Try rephrasing the question with the exact table or column names."
    )
    return {
        "answer": answer,
        "explanation": answer,
        "agent_log": _log(state, "failed", problem),
    }


# ---- Routing ----

def _after_execute(state: AgentState) -> str:
    if not state.get("execution_error") and not state.get("validation_errors"):
        return "analyze"
    if state.get("retries", 0) < settings.max_sql_retries:
        return "correct"
    return "failed"


# ---- Graph builder ----

def build_sql_expert(llm):
    """Build the SQL Expert sub-graph."""
    g = StateGraph(AgentState)
    g.add_node("understand", lambda s: understand(s, llm))
    g.add_node("fetch_schema", lambda s: fetch_schema(s, llm))
    g.add_node("generate_sql", lambda s: generate_sql(s, llm))
    g.add_node("execute", lambda s: validate_and_execute(s, llm))
    g.add_node("correct_sql", lambda s: correct_sql(s, llm))
    g.add_node("analyze", lambda s: analyze(s, llm))
    g.add_node("visualize", lambda s: visualize(s, llm))
    g.add_node("failed", lambda s: failed(s, llm))

    g.set_entry_point("understand")
    g.add_edge("understand", "fetch_schema")
    g.add_edge("fetch_schema", "generate_sql")
    g.add_edge("generate_sql", "execute")
    g.add_conditional_edges(
        "execute",
        _after_execute,
        {"analyze": "analyze", "correct": "correct_sql", "failed": "failed"},
    )
    g.add_edge("correct_sql", "execute")
    g.add_edge("analyze", "visualize")
    g.add_edge("visualize", END)
    g.add_edge("failed", END)
    return g.compile()


def run_sql_expert(state: AgentState, llm) -> AgentState:
    """Run the SQL Expert agent and return updated state."""
    graph = build_sql_expert(llm)
    return graph.invoke(state)
