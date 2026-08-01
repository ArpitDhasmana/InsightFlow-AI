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
    dimension = intent.get("dimension")

    # KPI marker (the frontend builds interactive KPI tiles from the kpis block).
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
        dim_title = (dimension or "group").title()

        if dimension == "month":
            series = [{"name": metric, "data": data}]
            if forecast.get("available"):
                proj = forecast["projection"]
                labels = labels + [f"+{i+1}m" for i in range(len(proj))]
                series[0]["data"] = data + [None] * len(proj)
                series.append({"name": "forecast", "data": [None] * len(data) + proj})
            charts.append({"type": "line", "title": f"{metric.title()} Trend", "labels": labels, "series": series})
        else:
            # Horizontal bar reads better for rankings; vertical bar for comparisons.
            is_ranking = intent.get("intent_type") == "ranking"
            charts.append(
                {
                    "type": "hbar" if is_ranking else "bar",
                    "title": f"{metric.title()} by {dim_title}",
                    "labels": labels,
                    "series": [{"name": metric, "data": data}],
                }
            )
            # A share/composition view makes sense for a small number of categories.
            if 2 <= len(rows) <= 8:
                charts.append(
                    {
                        "type": "doughnut",
                        "title": f"{metric.title()} Share by {dim_title}",
                        "labels": labels,
                        "series": [{"name": metric, "data": data}],
                    }
                )

    state["charts"] = charts
    return state
