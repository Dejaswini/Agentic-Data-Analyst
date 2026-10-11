"""Orchestrator Agent — the supervisor that routes questions to specialist agents.

Classification:
- 'query'       → SQL Expert (simple data retrieval)
- 'statistical' → Statistician (forecasts, trends, anomalies)
- 'exploration' → Explorer (autonomous pattern discovery)
- 'goal'        → Goal decomposition → multiple agents → synthesis
- 'report'      → Report Builder (multi-section reports)
- 'chat'        → direct reply (greetings, small talk, questions about the assistant)
"""
from __future__ import annotations

import json
import re

from langgraph.graph import END, StateGraph

from app.agents.state import AgentState
from app.agents.sql_expert import run_sql_expert
from app.agents.statistician import run_statistician
from app.agents.explorer import run_explorer
from app.agents.report_builder import run_report_builder
from app.llm import build_llm


def _log(state: AgentState, action: str, detail: str = "") -> list[dict]:
    log = list(state.get("agent_log") or [])
    log.append({"agent": "orchestrator", "action": action, "detail": detail})
    return log


# ---- Nodes ----

def classify(state: AgentState, llm) -> dict:
    """Classify the question to determine which agent(s) to invoke."""
    prompt = (
        "Classify this data analysis question into exactly ONE category.\n"
        "Categories:\n"
        "- query: simple data retrieval (who, what, how much, list, show me)\n"
        "- statistical: needs statistical analysis, forecasting, predictions, "
        "anomaly detection, growth rates, seasonality\n"
        "- exploration: broad exploration ('explore', 'find interesting', "
        "'what's notable', 'discover patterns', 'any insights')\n"
        "- goal: complex goal needing multi-step analysis ('help me increase', "
        "'why is X declining', 'how to improve', 'strategy for')\n"
        "- report: requests a report or comprehensive analysis ('report', "
        "'full analysis', 'summary of', 'overview')\n"
        "- chat: greetings, thanks, small talk, or questions about the assistant "
        "or about the previous answer that need NO database access ('hi', "
        "'hello', 'thanks', 'what can you do', 'explain that')\n\n"
        "Output ONLY the category name, nothing else.\n\n"
        f"Question: {state['question']}"
    )
    resp = llm.invoke(prompt)
    task_type = resp.content.strip().lower().strip("\"'.,")

    # Validate — keyword fallback
    valid = {"query", "statistical", "exploration", "goal", "report", "chat"}
    if task_type not in valid:
        q = state["question"].lower()
        if re.fullmatch(r"\W*(hi|hello|hey|thanks|thank you|ok|okay|bye)\W*", q):
            task_type = "chat"
        elif any(kw in q for kw in
               ["forecast", "predict", "trend", "growth", "anomal",
                "seasonal"]):
            task_type = "statistical"
        elif any(kw in q for kw in
                 ["explore", "discover", "interesting", "pattern", "insight"]):
            task_type = "exploration"
        elif any(kw in q for kw in
                 ["report", "overview", "summary", "comprehensive"]):
            task_type = "report"
        elif any(kw in q for kw in
                 ["help me", "how to", "improve", "increase", "why is",
                  "strategy"]):
            task_type = "goal"
        else:
            task_type = "query"

    return {
        "task_type": task_type,
        "agent_log": _log(state, "classify", task_type),
    }


def route_to_agent(state: AgentState) -> str:
    """Route to the appropriate agent based on classification."""
    return state.get("task_type", "query")


# ---- Specialist wrappers ----

def run_query_agent(state: AgentState, llm) -> dict:
    result = run_sql_expert(state, llm)
    return {k: v for k, v in result.items() if v is not None}


def run_stats_agent(state: AgentState, llm) -> dict:
    result = run_statistician(state, llm)
    return {k: v for k, v in result.items() if v is not None}


def run_explore_agent(state: AgentState, llm) -> dict:
    result = run_explorer(state, llm)
    return {k: v for k, v in result.items() if v is not None}


def run_report_agent(state: AgentState, llm) -> dict:
    result = run_report_builder(state, llm)
    return {k: v for k, v in result.items() if v is not None}


def run_chat(state: AgentState, llm) -> dict:
    """Direct conversational reply - no SQL, no table, no chart."""
    turns = "\n".join(
        f"User: {h.get('question', '')}\nAssistant: {h.get('answer', '')}"
        for h in (state.get("history") or [])[-6:]
    )
    prompt = (
        "You are a friendly data analyst assistant connected to a sales "
        "database (regions, customers, products, sales representatives, "
        "sales). Reply briefly and naturally to the user's message. Do not "
        "invent any numbers. If it is a greeting, greet back and suggest 2-3 "
        "example questions they could ask about the sales data.\n\n"
        f"Conversation so far:\n{turns}\n\n"
        f"User: {state['question']}"
    )
    resp = llm.invoke(prompt)
    return {
        "answer": resp.content,
        "explanation": resp.content,
        "agent_log": _log(state, "chat", "direct reply, no SQL"),
    }


# ---- Goal-oriented flow ----

def decompose_goal(state: AgentState, llm) -> dict:
    """Decompose a complex goal into sub-tasks for multiple agents."""
    prompt = (
        "You are a senior data analyst planning a multi-step investigation.\n"
        "Break this goal into 3-5 specific, concrete sub-questions that can "
        "each be answered with a single SQL query or statistical analysis.\n\n"
        'Output as a JSON array: '
        '[{"question": "...", "type": "query|statistical"}]\n\n'
        f"Goal: {state['question']}"
    )
    resp = llm.invoke(prompt)

    try:
        text = resp.content
        match = re.search(r"\[.*\]", text, re.S)
        sub_tasks = json.loads(match.group()) if match else json.loads(text)
    except (json.JSONDecodeError, AttributeError):
        sub_tasks = [{"question": state["question"], "type": "query"}]

    return {
        "sub_tasks": sub_tasks,
        "agent_log": _log(
            state, "decompose_goal", f"{len(sub_tasks)} sub-tasks"
        ),
    }


def execute_goal_plan(state: AgentState, llm) -> dict:
    """Execute each sub-task in the goal plan."""
    sub_tasks = state.get("sub_tasks", [])
    all_findings: list[dict] = []
    all_charts = list(state.get("charts") or [])

    for task in sub_tasks:
        q = task.get("question", "")
        t = task.get("type", "query")
        sub_state: AgentState = {
            "question": q,
            "history": state.get("history", []),
            "agent_log": [],
            "charts": [],
        }

        if t == "statistical":
            result = run_statistician(sub_state, llm)
        else:
            result = run_sql_expert(sub_state, llm)

        all_findings.append({
            "question": q,
            "answer": result.get("answer", ""),
            "sql": result.get("sql", ""),
            "columns": result.get("columns", []),
            "rows": (result.get("rows") or [])[:20],
        })
        all_charts.extend(result.get("charts") or [])

    return {
        "discoveries": all_findings,
        "charts": all_charts,
        "agent_log": _log(
            state, "execute_goal_plan", f"{len(all_findings)} findings"
        ),
    }


def synthesize_goal(state: AgentState, llm) -> dict:
    """Synthesize all goal findings into a cohesive response."""
    findings = state.get("discoveries", [])
    findings_text = "\n\n".join(
        f"### Sub-question: {f['question']}\nFinding: {f['answer']}"
        for f in findings
    )

    prompt = (
        "You are a senior data analyst. Synthesize these findings into a "
        "cohesive, actionable response to the user's original goal.\n\n"
        "Include:\n"
        "1. Direct answer to their goal\n"
        "2. Key data points that support your analysis\n"
        "3. 3-4 specific, actionable recommendations\n\n"
        "Use ONLY the data provided. Indian formats (lakh, crore) are fine.\n\n"
        f"Original goal: {state['question']}\n\n"
        f"Findings:\n{findings_text}"
    )
    resp = llm.invoke(prompt)
    return {
        "answer": resp.content,
        "explanation": resp.content,
        "agent_log": _log(state, "synthesize_goal"),
    }


# ---- Graph builder ----

def build_orchestrator(llm=None):
    """Build the top-level orchestrator graph."""
    llm = llm or build_llm()
    g = StateGraph(AgentState)

    g.add_node("classify", lambda s: classify(s, llm))
    g.add_node("query", lambda s: run_query_agent(s, llm))
    g.add_node("statistical", lambda s: run_stats_agent(s, llm))
    g.add_node("exploration", lambda s: run_explore_agent(s, llm))
    g.add_node("report", lambda s: run_report_agent(s, llm))
    g.add_node("chat", lambda s: run_chat(s, llm))
    g.add_node("decompose_goal", lambda s: decompose_goal(s, llm))
    g.add_node("execute_goal", lambda s: execute_goal_plan(s, llm))
    g.add_node("synthesize_goal", lambda s: synthesize_goal(s, llm))

    g.set_entry_point("classify")
    g.add_conditional_edges(
        "classify",
        route_to_agent,
        {
            "query": "query",
            "statistical": "statistical",
            "exploration": "exploration",
            "report": "report",
            "chat": "chat",
            "goal": "decompose_goal",
        },
    )
    g.add_edge("query", END)
    g.add_edge("statistical", END)
    g.add_edge("exploration", END)
    g.add_edge("report", END)
    g.add_edge("chat", END)
    g.add_edge("decompose_goal", "execute_goal")
    g.add_edge("execute_goal", "synthesize_goal")
    g.add_edge("synthesize_goal", END)

    return g.compile()


def ask(
    question: str,
    history: list[dict[str, str]] | None = None,
    llm=None,
) -> AgentState:
    """Main entry point — routes through the orchestrator."""
    graph = build_orchestrator(llm)
    return graph.invoke({
        "question": question,
        "history": history or [],
        "retries": 0,
        "agent_log": [],
        "charts": [],
    })
