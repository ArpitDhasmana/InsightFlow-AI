"""Visualization Agent.

Produces chart specifications (consumed by the frontend / any charting library)
based on the intent and retrieved rows. Returns KPI cards plus a primary chart.
"""
from __future__ import annotations

from .state import PipelineState


def run(state: PipelineState) -> PipelineState:
    rows = state.get("rows", [])
    intent = state["intent"]
    kpis = state.get("kpis", {})
    forecast = state.get("forecast", {})
    charts: list[dict] = []

    value_key = kpis.get("value_key")
    metric = intent["metric"]

    # KPI card.
    charts.append(
        {
            "type": "kpi",
            "title": f"Total {metric.title()}",
            "labels": ["total"],
            "series": [{"name": metric, "data": [kpis.get("total", 0)]}],
        }
    )

    if rows and value_key:
        label_key = next((k for k, v in rows[0].items() if isinstance(v, str)), None)
        labels = [str(r.get(label_key, i)) for i, r in enumerate(rows)]
        data = [round(float(r[value_key]), 2) for r in rows]

        if intent.get("dimension") == "month":
            series = [{"name": metric, "data": data}]
            if forecast.get("available"):
                pad = [None] * len(data)
                proj = forecast["projection"]
                labels = labels + [f"+{i+1}m" for i in range(len(proj))]
                series[0]["data"] = data + [None] * len(proj)
                series.append({"name": "forecast", "data": pad + proj})
            charts.append({"type": "line", "title": f"{metric.title()} Trend", "labels": labels, "series": series})
        else:
            charts.append(
                {
                    "type": "bar",
                    "title": f"{metric.title()} by {intent.get('dimension', 'group').title()}",
                    "labels": labels,
                    "series": [{"name": metric, "data": data}],
                }
            )

    state["charts"] = charts
    return state
