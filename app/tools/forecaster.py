"""Time series forecasting — linear regression + simple exponential smoothing.

No heavy ML dependencies: uses numpy for polyfit and a hand-rolled SES.
Returns historical values, forecast, and 95 % confidence intervals.
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from app.tools import registry


def _exponential_smoothing(values: list[float], alpha: float = 0.3) -> list[float]:
    """Simple exponential smoothing (SES)."""
    result = [values[0]]
    for i in range(1, len(values)):
        result.append(alpha * values[i] + (1 - alpha) * result[-1])
    return result


@registry.register(
    "forecast_timeseries",
    "Forecast future values for a time series using an ensemble of linear "
    "regression and exponential smoothing.  Returns predicted values with "
    "95 % confidence intervals.",
    category="analysis",
    parameters={
        "columns": "column names",
        "rows": "row data",
        "date_col": "date column",
        "value_col": "numeric column",
        "periods": "number of future periods to forecast (default 6)",
    },
)
def forecast_timeseries(
    columns: list[str],
    rows: list[list],
    date_col: str,
    value_col: str,
    periods: int = 6,
) -> dict:
    df = pd.DataFrame(rows, columns=columns)
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    df = (
        df.dropna(subset=[date_col, value_col])
        .sort_values(date_col)
        .reset_index(drop=True)
    )

    if len(df) < 3:
        return {
            "success": False,
            "error": "Need at least 3 data points for forecasting",
        }

    values = df[value_col].values.astype(float)
    x = np.arange(len(values), dtype=float)

    # ---- Linear regression ----
    coeffs = np.polyfit(x, values, 1)
    slope, intercept = float(coeffs[0]), float(coeffs[1])
    fitted = np.polyval(coeffs, x)
    residuals = values - fitted
    std_err = float(np.std(residuals))

    future_x = np.arange(len(values), len(values) + periods, dtype=float)
    linear_forecast = np.polyval(coeffs, future_x)

    # ---- Exponential smoothing ----
    smoothed = _exponential_smoothing(values.tolist())
    last_smooth = smoothed[-1]
    es_forecast = [last_smooth] * periods          # flat forecast for SES

    # ---- Ensemble (average) ----
    ensemble = [(l + e) / 2 for l, e in zip(linear_forecast, es_forecast)]

    # ---- Future dates ----
    last_date = df[date_col].max()
    avg_gap = (
        df[date_col].diff().dropna().mean()
        if len(df) >= 2
        else timedelta(days=30)
    )
    future_dates = [last_date + avg_gap * (i + 1) for i in range(periods)]

    # ---- 95 % confidence interval ----
    ci_95 = 1.96 * std_err
    lower = [round(v - ci_95, 2) for v in ensemble]
    upper = [round(v + ci_95, 2) for v in ensemble]

    return {
        "success": True,
        "method": "ensemble (linear regression + exponential smoothing)",
        "historical": {
            "dates": [
                str(d.date()) if hasattr(d, "date") else str(d)
                for d in df[date_col]
            ],
            "values": [round(float(v), 2) for v in values],
        },
        "forecast": {
            "dates": [
                str(d.date()) if hasattr(d, "date") else str(d)
                for d in future_dates
            ],
            "values": [round(float(v), 2) for v in ensemble],
            "lower_ci": lower,
            "upper_ci": upper,
        },
        "trend_slope": round(slope, 2),
        "trend_direction": (
            "increasing" if slope > 0 else "decreasing" if slope < 0 else "flat"
        ),
        "confidence_level": "95%",
    }
