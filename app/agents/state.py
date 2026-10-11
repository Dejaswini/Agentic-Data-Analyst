"""Extended state for the multi-agent orchestrator.

Carries data through all specialist agents: SQL Expert, Statistician,
Explorer, and Report Builder.
"""
from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # ---- Input ----
    question: str
    history: list[dict[str, str]]

    # ---- Orchestrator ----
    task_type: str                          # query | statistical | exploration | goal | report
    sub_tasks: list[dict[str, Any]]         # decomposed plan for goal-oriented analysis
    current_step: int
    agent_log: list[dict[str, Any]]         # transparency log of agent/tool calls

    # ---- SQL Expert ----
    intent: str
    schema_info: str
    sql: str
    validation_errors: list[str]
    columns: list[str]
    rows: list[list[Any]]
    execution_error: str
    retries: int

    # ---- Statistician ----
    stats_results: dict[str, Any]           # output of statistical analyses
    forecast_data: dict[str, Any]           # time-series forecast

    # ---- Explorer ----
    discoveries: list[dict[str, Any]]       # ranked discoveries with charts

    # ---- Report Builder ----
    report_sections: list[dict[str, Any]]   # multi-section report data

    # ---- Output ----
    explanation: str
    charts: list[dict[str, Any]]            # multiple charts (bar, line, pie, forecast, …)
    answer: str
