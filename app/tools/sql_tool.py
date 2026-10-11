"""SQL query tool — validates and executes read-only queries."""
from __future__ import annotations

from app.tools import registry
from app.db import run_query, get_schema, schema_text
from app.sql_validator import validate_sql


@registry.register(
    "sql_query",
    "Validate and execute a read-only SQL SELECT query against the PostgreSQL "
    "database. Returns columns and rows.",
    category="data",
    parameters={"sql": "The SQL SELECT query to execute"},
)
def sql_query_tool(sql: str) -> dict:
    schema = get_schema()
    result = validate_sql(sql, schema)
    if not result.ok:
        return {"success": False, "errors": result.errors, "columns": [], "rows": []}
    try:
        cols, rows = run_query(sql)
        return {
            "success": True,
            "columns": cols,
            "rows": [list(r) for r in rows],
            "row_count": len(rows),
        }
    except Exception as exc:
        return {"success": False, "errors": [str(exc)], "columns": [], "rows": []}


@registry.register(
    "get_schema",
    "Retrieve the database schema (tables, columns, relationships). "
    "Use this before writing SQL.",
    category="data",
)
def get_schema_tool() -> dict:
    return {"schema": get_schema(), "schema_text": schema_text()}
