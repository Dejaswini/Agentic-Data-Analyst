"""Anomaly detection — IQR-based outliers and period-over-period spike
detection.

Works on raw query results (columns + rows).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.tools import registry


@registry.register(
    "detect_outliers",
    "Detect statistical outliers in a numeric column using the IQR method.",
    category="analysis",
    parameters={
        "columns": "column names",
        "rows": "row data",
        "value_col": "column to check for outliers",
    },
)
def detect_outliers(
    columns: list[str], rows: list[list], value_col: str
) -> dict:
    df = pd.DataFrame(rows, columns=columns)
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    series = df[value_col].dropna()

    if len(series) < 4:
        return {
            "success": False,
            "error": "Need at least 4 data points for outlier detection",
        }

    q1 = float(series.quantile(0.25))
    q3 = float(series.quantile(0.75))
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr

    outlier_mask = (series < lower_bound) | (series > upper_bound)
    outlier_rows = df[outlier_mask].to_dict("records")

    return {
        "success": True,
        "method": "IQR (1.5× interquartile range)",
        "bounds": {
            "lower": round(lower_bound, 2),
            "upper": round(upper_bound, 2),
        },
        "outlier_count": int(outlier_mask.sum()),
        "total_count": int(len(series)),
        "outlier_pct": round(float(outlier_mask.sum()) / len(series) * 100, 1),
        "outliers": outlier_rows[:20],
    }


@registry.register(
    "detect_spikes",
    "Detect sudden spikes or drops in a time series (period-over-period "
    "changes exceeding a threshold).",
    category="analysis",
    parameters={
        "columns": "column names",
        "rows": "row data",
        "date_col": "date column",
        "value_col": "numeric column",
        "threshold_pct": "% change threshold to flag (default 30)",
    },
)
def detect_spikes(
    columns: list[str],
    rows: list[list],
    date_col: str,
    value_col: str,
    threshold_pct: float = 30,
) -> dict:
    df = pd.DataFrame(rows, columns=columns)
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    df = (
        df.dropna(subset=[date_col, value_col])
        .sort_values(date_col)
        .reset_index(drop=True)
    )

    if len(df) < 2:
        return {"success": False, "error": "Need at least 2 data points"}

    spikes: list[dict] = []
    values = df[value_col].tolist()
    dates = df[date_col].tolist()
    for i in range(1, len(values)):
        if values[i - 1] != 0:
            pct_change = (
                (values[i] - values[i - 1]) / abs(values[i - 1]) * 100
            )
            if abs(pct_change) >= threshold_pct:
                spikes.append({
                    "date": str(
                        dates[i].date()
                        if hasattr(dates[i], "date")
                        else dates[i]
                    ),
                    "value": float(values[i]),
                    "prev_value": float(values[i - 1]),
                    "change_pct": round(pct_change, 1),
                    "type": "spike" if pct_change > 0 else "drop",
                })

    return {
        "success": True,
        "threshold_pct": threshold_pct,
        "spike_count": len(spikes),
        "spikes": spikes,
    }
