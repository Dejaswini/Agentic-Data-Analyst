"""PostgreSQL access: schema introspection and read-only query execution."""
from __future__ import annotations

import functools
from typing import Any

import psycopg

from app.config import settings

# Tables the agent is allowed to see (demo schema).
ALLOWED_TABLES = [
    "regions",
    "customers",
    "products",
    "sales_representatives",
    "sales",
]


def get_connection() -> psycopg.Connection:
    return psycopg.connect(settings.database_url)


@functools.lru_cache(maxsize=1)
def get_schema() -> dict[str, list[str]]:
    """Return {table: [column, ...]} for the allowed tables."""
    schema: dict[str, list[str]] = {}
    with get_connection() as conn, conn.cursor() as cur:
        for table in ALLOWED_TABLES:
            cur.execute(
                """SELECT column_name FROM information_schema.columns
                   WHERE table_schema = 'public' AND table_name = %s
                   ORDER BY ordinal_position""",
                (table,),
            )
            schema[table] = [r[0] for r in cur.fetchall()]
    return schema


def schema_text(schema: dict[str, list[str]] | None = None) -> str:
    """Human-readable schema for LLM prompts, with helpful notes."""
    schema = schema or get_schema()
    lines = ["PostgreSQL database 'sales_db' tables:"]
    for table, cols in schema.items():
        lines.append(f"- {table}({', '.join(cols)})")
    lines += [
        "",
        "Relationships:",
        "- sales.customer_id -> customers.customer_id",
        "- sales.product_id -> products.product_id",
        "- sales.rep_id -> sales_representatives.rep_id",
        "- customers.region_id -> regions.region_id",
        "- sales_representatives.region_id -> regions.region_id",
        "Notes:",
        "- sales.total_amount = quantity * unit_price (money, in rupees)",
        "- sales.sale_date is a DATE (2024-01-01 .. 2026-09-27)",
        "- 'revenue'/'sales amount' means SUM(sales.total_amount)",
        "- Regions are identified by regions.region_name or regions.state "
        "(e.g. 'Tamil Nadu' is a state with several regions)",
    ]
    return "\n".join(lines)


def run_query(sql: str, row_cap: int = 500) -> tuple[list[str], list[tuple[Any, ...]]]:
    """Execute a validated read-only query. Returns (columns, rows)."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute(sql)
        cols = [d.name for d in cur.description]
        rows = cur.fetchmany(row_cap)
    return cols, rows
