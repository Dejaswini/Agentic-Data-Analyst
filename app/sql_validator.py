"""Read-only SQL validation for the agentic data analyst.

Rules:
- exactly ONE statement
- statement must be a SELECT (WITH ... SELECT is allowed)
- no data/schema mutation or unsafe commands anywhere in the tree
- every referenced table must exist in the demo schema
- every referenced column must exist in a referenced table (best effort)

Implemented with sqlglot (dialect: postgres).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

# Node types that are never allowed, wherever they appear.
FORBIDDEN_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Create,
    exp.TruncateTable,
    exp.Grant,
    exp.Revoke,
    exp.Merge,
    exp.Command,       # VACUUM, COPY, CALL, SET, etc.
    exp.Transaction,
    exp.Lock,
    exp.Commit,
    exp.Rollback,
    exp.AddConstraint,
    exp.Set,
    exp.UserDefinedFunction,
    exp.Copy,
)

# Functions that can write files or read the server filesystem.
FORBIDDEN_FUNCTIONS = {
    "pg_read_file", "pg_write_file", "pg_ls_dir", "lo_import", "lo_export",
    "copy", "pg_terminate_backend", "pg_cancel_backend", "set_config",
    "dblink", "pg_sleep",
}


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)


def validate_sql(sql: str, schema: dict[str, list[str]]) -> ValidationResult:
    errors: list[str] = []

    try:
        statements = [st for st in sqlglot.parse(sql, read="postgres") if st is not None]
    except sqlglot.errors.SqlglotError as exc:
        return ValidationResult(False, [f"Could not parse the SQL: {exc}"])
    if not statements:
        return ValidationResult(False, ["Could not parse the SQL."])
    if len(statements) > 1:
        return ValidationResult(False, ["Only one statement is allowed."])

    tree = statements[0]

    # Must be a SELECT (optionally under WITH / parentheses).
    core = tree
    while isinstance(core, (exp.With, exp.Paren, exp.Subquery, exp.Alias)):
        core = core.this
    if not isinstance(core, exp.Select):
        return ValidationResult(False, ["Only SELECT queries are allowed."])

    # No mutating / unsafe constructs anywhere.
    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            errors.append(f"Forbidden statement: {type(node).__name__}")
    for func in tree.find_all(exp.Func):
        name = (getattr(func, "name", "") or func.sql_name() or "").lower()
        if name in FORBIDDEN_FUNCTIONS:
            errors.append(f"Forbidden function: {name}")
    # SELECT INTO creates a table - not allowed.
    if core.args.get("into") is not None:
        errors.append("SELECT INTO is not allowed.")

    # CTEs act as local tables with their own output columns.
    cte_cols: dict[str, set[str]] = {}
    for cte in tree.find_all(exp.CTE):
        inner = cte.this
        cols = {
            (e.alias_or_name or "").lower()
            for e in getattr(inner, "expressions", [])
        } - {""}
        cte_cols[cte.alias.lower()] = cols

    # Table existence.
    known_tables = {t.lower(): t for t in schema}
    for table in tree.find_all(exp.Table):
        name = (table.name or "").lower()
        if name not in known_tables and name not in cte_cols:
            errors.append(f"Unknown table: {table.name}")

    # Column existence (best effort).
    alias_map: dict[str, str] = {}
    for table in tree.find_all(exp.Table):
        real = table.name
        alias_map[real.lower()] = real
        if table.alias:
            alias_map[table.alias.lower()] = real
    schema_lower = {t.lower(): {c.lower() for c in cols} for t, cols in schema.items()}
    schema_lower.update(cte_cols)
    referenced = {t for t in alias_map if t in schema_lower}

    # Projection aliases (SELECT ... AS revenue) are valid in ORDER BY etc.
    output_aliases = {
        (a.alias_or_name or "").lower() for a in tree.find_all(exp.Alias)
    } - {""}

    for col in tree.find_all(exp.Column):
        col_name = (col.name or "").lower()
        if col_name == "*" or col_name in output_aliases:
            continue
        if col.table:
            real_table = alias_map.get(col.table.lower())
            if real_table and real_table.lower() in schema_lower:
                if col_name not in schema_lower[real_table.lower()]:
                    errors.append(f"Unknown column: {col.table}.{col.name}")
            # unknown aliases were already caught by the table check
        elif referenced:
            if not any(col_name in schema_lower[t] for t in referenced):
                errors.append(f"Unknown column: {col.name}")

    # Deduplicate while keeping order.
    seen: set[str] = set()
    unique_errors = [e for e in errors if not (e in seen or seen.add(e))]
    return ValidationResult(not unique_errors, unique_errors)
