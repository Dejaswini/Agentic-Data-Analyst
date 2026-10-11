"""Statistical analysis tools — summary stats, growth rates, seasonality,
correlations.

All functions accept raw columns+rows so they work with any query result.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.tools import registry


def _to_dataframe(columns: list[str], rows: list[list[Any]]) -> pd.DataFrame:
    """Convert columns+rows to a DataFrame, coercing numerics."""
    df = pd.DataFrame(rows, columns=columns)
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="ignore")
    return df


# ---------- Summary statistics ----------

@registry.register(
    "summary_statistics",
    "Compute summary statistics (mean, median, std, min, max, percentiles) "
    "for a numeric column.",
    category="analysis",
    parameters={
        "columns": "list of column names",
        "rows": "list of row lists",
        "value_col": "column to analyze",
    },
)
def summary_statistics(
    columns: list[str], rows: list[list], value_col: str
) -> dict:
    df = _to_dataframe(columns, rows)
    if value_col not in df.columns:
        return {"success": False, "error": f"Column '{value_col}' not found"}
    series = pd.to_numeric(df[value_col], errors="coerce").dropna()
    if series.empty:
        return {"success": False, "error": "No numeric values in column"}
    return {
        "success": True,
        "count": int(len(series)),
        "mean": round(float(series.mean()), 2),
        "median": round(float(series.median()), 2),
        "std": round(float(series.std()), 2),
        "min": round(float(series.min()), 2),
        "max": round(float(series.max()), 2),
        "p25": round(float(series.quantile(0.25)), 2),
        "p75": round(float(series.quantile(0.75)), 2),
        "p90": round(float(series.quantile(0.90)), 2),
    }


# ---------- Growth rates ----------

@registry.register(
    "growth_rates",
    "Calculate period-over-period growth rates (MoM, YoY) for time series "
    "data.",
    category="analysis",
    parameters={
        "columns": "column names",
        "rows": "row data",
        "date_col": "date column",
        "value_col": "numeric column",
    },
)
def growth_rates(
    columns: list[str], rows: list[list], date_col: str, value_col: str
) -> dict:
    df = _to_dataframe(columns, rows)
    if date_col not in df.columns or value_col not in df.columns:
        return {"success": False, "error": "Required columns not found"}
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).sort_values(date_col)
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")

    rates: list[dict] = []
    values = df[value_col].tolist()
    dates = df[date_col].tolist()
    for i in range(1, len(values)):
        if values[i - 1] and values[i - 1] != 0:
            pct = round(
                (values[i] - values[i - 1]) / abs(values[i - 1]) * 100, 2
            )
            rates.append({
                "period": str(
                    dates[i].date() if hasattr(dates[i], "date") else dates[i]
                ),
                "value": float(values[i]),
                "prev_value": float(values[i - 1]),
                "growth_pct": pct,
            })

    avg_growth = (
        round(float(np.mean([r["growth_pct"] for r in rates])), 2) if rates else 0
    )
    return {
        "success": True,
        "rates": rates,
        "avg_growth_pct": avg_growth,
        "periods": len(rates),
    }


# ---------- Seasonality ----------

@registry.register(
    "detect_seasonality",
    "Detect monthly/quarterly seasonal patterns in time series data.",
    category="analysis",
    parameters={
        "columns": "column names",
        "rows": "row data",
        "date_col": "date column",
        "value_col": "numeric column",
    },
)
def detect_seasonality(
    columns: list[str], rows: list[list], date_col: str, value_col: str
) -> dict:
    df = _to_dataframe(columns, rows)
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col])
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    df["month"] = df[date_col].dt.month

    monthly_avg = df.groupby("month")[value_col].mean()
    overall_avg = monthly_avg.mean()
    if overall_avg == 0:
        return {"success": False, "error": "Overall average is zero"}
    seasonal_index = (monthly_avg / overall_avg).round(3)

    peak_month = int(seasonal_index.idxmax())
    trough_month = int(seasonal_index.idxmin())
    _MONTH_NAMES = {
        1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
        7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
    }

    return {
        "success": True,
        "seasonal_index": {
            _MONTH_NAMES.get(k, str(k)): float(v)
            for k, v in seasonal_index.items()
        },
        "peak_month": _MONTH_NAMES.get(peak_month, str(peak_month)),
        "trough_month": _MONTH_NAMES.get(trough_month, str(trough_month)),
        "seasonality_strength": round(
            float(seasonal_index.max() - seasonal_index.min()), 3
        ),
    }


# ---------- Correlations ----------

@registry.register(
    "correlation_analysis",
    "Find correlations between numeric columns in a dataset.",
    category="analysis",
    parameters={"columns": "column names", "rows": "row data"},
)
def correlation_analysis(columns: list[str], rows: list[list]) -> dict:
    df = _to_dataframe(columns, rows)
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if len(numeric_cols) < 2:
        return {
            "success": False,
            "error": "Need at least 2 numeric columns for correlation",
        }
    corr = df[numeric_cols].corr().round(3)
    notable: list[dict] = []
    for i, c1 in enumerate(numeric_cols):
        for c2 in numeric_cols[i + 1 :]:
            r = float(corr.loc[c1, c2])
            if abs(r) > 0.5:
                notable.append({
                    "col1": c1,
                    "col2": c2,
                    "correlation": r,
                    "strength": "strong" if abs(r) > 0.7 else "moderate",
                })
    return {
        "success": True,
        "correlation_matrix": {
            c: {c2: float(corr.loc[c, c2]) for c2 in numeric_cols}
            for c in numeric_cols
        },
        "notable_correlations": notable,
    }
