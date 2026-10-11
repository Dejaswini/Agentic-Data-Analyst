"""Chart-type selection: from the user's words first, then the result shape.

    comparison / top-N / highest / lowest  -> bar
    trend / over time / monthly            -> line
    share / composition / percentage       -> pie
    relationship / correlation             -> scatter
    explicit request ("as a line chart")   -> user override wins
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from numbers import Number
from typing import Any, Sequence

CHART_TYPES = ("bar", "line", "pie", "scatter", "table", "forecast")

_OVERRIDE_PATTERNS = [
    (re.compile(r"\bbar(\s*chart|\s*graph)?\b", re.I), "bar"),
    (re.compile(r"\bline(\s*chart|\s*graph)?\b", re.I), "line"),
    (re.compile(r"\bpie(\s*chart)?\b|\bdonut\b", re.I), "pie"),
    (re.compile(r"\bscatter(\s*plot|\s*chart)?\b", re.I), "scatter"),
    (re.compile(r"\bforecast(\s*chart|\s*graph)?\b", re.I), "forecast"),
    (re.compile(r"\b(table|tabular)\b", re.I), "table"),
]

_TREND = re.compile(
    r"\b(trend|over time|monthly|weekly|daily|yearly|per month|per year|"
    r"each month|by month|by year|growth|across months)\b", re.I)
_SHARE = re.compile(
    r"\b(share|composition|percentage|percent|proportion|distribution|"
    r"breakdown|split|contribution)\b", re.I)
_RELATION = re.compile(
    r"\b(relationship|correlation|correlated|vs\.?|versus|against)\b", re.I)
_COMPARE = re.compile(
    r"\b(compare|comparison|top|bottom|highest|lowest|best|worst|most|least|"
    r"rank|ranking|leading)\b", re.I)


@dataclass
class ChartSpec:
    type: str            # one of CHART_TYPES
    x: str | None = None
    y: str | None = None
    title: str = ""
    reason: str = ""     # shown in the UI for transparency


def _is_number(v: Any) -> bool:
    return isinstance(v, Number) and not isinstance(v, bool)


def _is_datelike(v: Any) -> bool:
    if isinstance(v, (date, datetime)):
        return True
    if isinstance(v, str):
        return bool(re.match(r"^\d{4}(-\d{2})?(-\d{2})?$", v))
    return False


def override_from_question(question: str) -> str | None:
    """Explicit chart type named in the question, e.g. 'show it as a pie chart'."""
    for pattern, chart in _OVERRIDE_PATTERNS:
        if pattern.search(question):
            return chart
    return None


def choose_chart(
    question: str,
    columns: Sequence[str],
    rows: Sequence[Sequence[Any]],
    override: str | None = None,
) -> ChartSpec:
    """Pick a chart for one result set. Falls back to a table."""
    override = override or override_from_question(question)
    if override in ("table",):
        return ChartSpec("table", reason="you asked for a table")

    if not rows or not columns:
        return ChartSpec("table", reason="no rows to plot")

    # Classify columns.
    sample = rows[0]
    numeric_idx = [i for i, v in enumerate(sample) if _is_number(v)]
    datelike_idx = [i for i, v in enumerate(sample) if _is_datelike(v)]
    text_idx = [i for i in range(len(columns))
                if i not in numeric_idx and i not in datelike_idx]

    def spec(t: str, x_i: int | None, y_i: int | None, why: str) -> ChartSpec:
        return ChartSpec(
            t,
            x=columns[x_i] if x_i is not None else None,
            y=columns[y_i] if y_i is not None else None,
            title=question.strip().rstrip("?"),
            reason=why,
        )

    # Explicit user/agent override gets the best-matching axes.
    if override in CHART_TYPES:
        x_i = (datelike_idx or text_idx or [None])[0] if override != "scatter" else (numeric_idx + [None])[0]
        if override == "scatter" and len(numeric_idx) >= 2:
            return spec("scatter", numeric_idx[0], numeric_idx[1], "you asked for a scatter plot")
        if override == "pie" and (text_idx or datelike_idx) and numeric_idx:
            return spec("pie", (text_idx + datelike_idx)[0], numeric_idx[0], "you asked for a pie chart")
        if override in ("bar", "line") and numeric_idx:
            x_pool = datelike_idx if override == "line" else (text_idx + datelike_idx)
            x_i = (x_pool or text_idx or datelike_idx or [None])[0]
            if x_i is not None:
                return spec(override, x_i, numeric_idx[0], f"you asked for a {override} chart")
        # cannot honour the override with this result shape -> fall through

    if not numeric_idx:
        return ChartSpec("table", reason="result has no numeric column to plot")

    # Question-driven choice.
    if _TREND.search(question) and datelike_idx:
        return spec("line", datelike_idx[0], numeric_idx[0], "trend question with a date column")
    if _SHARE.search(question) and (text_idx or datelike_idx):
        return spec("pie", (text_idx + datelike_idx)[0], numeric_idx[0], "share/composition question")
    if _RELATION.search(question) and len(numeric_idx) >= 2:
        return spec("scatter", numeric_idx[0], numeric_idx[1], "relationship between two numbers")

    # Shape-driven fallback.
    if datelike_idx and numeric_idx:
        return spec("line", datelike_idx[0], numeric_idx[0], "date column found - plotted as a trend")
    if text_idx and numeric_idx:
        return spec("bar", text_idx[0], numeric_idx[0], "categories with values - plotted as bars")

    return ChartSpec("table", reason="result shape did not fit a chart")
