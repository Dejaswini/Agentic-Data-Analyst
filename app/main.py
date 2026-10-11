"""FastAPI backend: multi-agent orchestrator with exploration and reports.

Run:  uvicorn app.main:app --reload
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.agents.orchestrator import ask
from app.db import get_schema
from app.tools import registry
from app.tools.history_search import store_analysis

# Import tools so they register themselves with the registry.
import app.tools.sql_tool          # noqa: F401
import app.tools.stats_engine      # noqa: F401
import app.tools.forecaster        # noqa: F401
import app.tools.anomaly_detector  # noqa: F401
import app.tools.history_search    # noqa: F401

app = FastAPI(
    title="Agentic Data Analyst",
    version="2.0.0",
    description="Multi-agent data analyst with SQL, statistics, exploration, "
    "and reporting",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory conversation store
_conversations: dict[str, list[dict[str, str]]] = {}
_MAX_TURNS = 20


# ---- Request / Response models ----

class AskRequest(BaseModel):
    question: str
    conversation_id: str | None = None


class AskResponse(BaseModel):
    conversation_id: str
    task_type: str = "query"
    answer: str
    sql: str = ""
    columns: list[str] = Field(default_factory=list)
    rows: list[list] = Field(default_factory=list)
    charts: list[dict] = Field(default_factory=list)
    stats_results: dict = Field(default_factory=dict)
    discoveries: list[dict] = Field(default_factory=list)
    report_sections: list[dict] = Field(default_factory=list)
    agent_log: list[dict] = Field(default_factory=list)
    retries: int = 0


# ---- Endpoints ----

@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": "2.0.0",
        "agents": [
            "orchestrator",
            "sql_expert",
            "statistician",
            "explorer",
            "report_builder",
        ],
    }


@app.get("/schema")
def schema() -> dict:
    return get_schema()


@app.get("/tools")
def list_tools() -> list[dict]:
    """List all registered tools the agents can use."""
    return [
        {
            "name": t.name,
            "description": t.description,
            "category": t.category,
        }
        for t in registry.list_tools()
    ]


@app.post("/ask", response_model=AskResponse)
def ask_endpoint(req: AskRequest) -> AskResponse:
    """Unified endpoint — the orchestrator classifies and routes."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="question is empty")

    conv_id = req.conversation_id or uuid.uuid4().hex
    history = _conversations.setdefault(conv_id, [])

    try:
        state = ask(req.question, history=history)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    answer = state.get("answer", "")
    history.append({"question": req.question, "answer": answer})
    del history[:-_MAX_TURNS]

    # Persist for history search
    store_analysis(
        conv_id,
        req.question,
        answer,
        sql=state.get("sql", ""),
        columns=state.get("columns"),
        rows=state.get("rows"),
    )

    return AskResponse(
        conversation_id=conv_id,
        task_type=state.get("task_type", "query"),
        answer=answer,
        sql=state.get("sql", ""),
        columns=state.get("columns", []),
        rows=state.get("rows", []),
        charts=state.get("charts", []),
        stats_results=state.get("stats_results", {}),
        discoveries=state.get("discoveries", []),
        report_sections=state.get("report_sections", []),
        agent_log=state.get("agent_log", []),
        retries=state.get("retries", 0),
    )
