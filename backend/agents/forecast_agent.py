"""Forecast Agent.

Projects future values from a time series using a lightweight linear trend fit
(ordinary least squares). Only produces a forecast when the question is about a
trend over time; otherwise returns an empty forecast.
"""
from __future__ import annotations

from .constants import FORECAST_DIMENSIONS
from .state import PipelineState


def _linear_forecast(values: list[float], horizon: int = 3) -> list[float]:
    n = len(values)
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(values) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        slope = 0.0
    else:
        slope = sum((xs[i] - mean_x) * (values[i] - mean_y) for i in range(n)) / denom
    intercept = mean_y - slope * mean_x
    return [round(intercept + slope * (n + h), 2) for h in range(horizon)]


def run(state: PipelineState) -> PipelineState:
    rows = state.get("rows", [])
    kpis = state.get("kpis", {})
    value_key = kpis.get("value_key")
    is_trend = state["intent"].get("dimension") in FORECAST_DIMENSIONS and not state["intent"].get("breakdown")

    if not is_trend or not value_key or len(rows) < 3:
        state["forecast"] = {"available": False}
        return state

    values = [float(r[value_key]) for r in rows]
    projection = _linear_forecast(values, horizon=3)
    last = values[-1]
    direction = "up" if projection[-1] > last else "down" if projection[-1] < last else "flat"

    state["forecast"] = {
        "available": True,
        "horizon_months": 3,
        "projection": projection,
        "direction": direction,
        "next_value": projection[0],
    }
    return state
