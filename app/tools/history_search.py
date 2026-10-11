"""In-memory analysis history for context and follow-ups.

Stores past analyses so the orchestrator can recall earlier findings
when the user asks follow-up questions.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.tools import registry

# In-memory store: {conversation_id: [analysis_entry]}
_history: dict[str, list[dict[str, Any]]] = {}
_MAX_HISTORY = 50


def store_analysis(
    conversation_id: str,
    question: str,
    answer: str,
    sql: str = "",
    columns: list[str] | None = None,
    rows: list[list] | None = None,
) -> None:
    """Store a completed analysis for future reference."""
    entries = _history.setdefault(conversation_id, [])
    entries.append({
        "question": question,
        "answer": answer,
        "sql": sql,
        "columns": columns or [],
        "rows": (rows or [])[:50],
        "timestamp": datetime.now().isoformat(),
    })
    del entries[:-_MAX_HISTORY]


@registry.register(
    "search_history",
    "Search past analyses in this conversation for context.  Useful for "
    "follow-up questions.",
    category="data",
    parameters={
        "conversation_id": "conversation to search",
        "query": "search keywords",
    },
)
def search_history(conversation_id: str, query: str = "") -> dict:
    entries = _history.get(conversation_id, [])
    if not query:
        return {"success": True, "results": entries[-5:], "total": len(entries)}
    query_lower = query.lower()
    matched = [
        e
        for e in entries
        if query_lower in e["question"].lower()
        or query_lower in e["answer"].lower()
    ]
    return {"success": True, "results": matched[-5:], "total": len(matched)}
