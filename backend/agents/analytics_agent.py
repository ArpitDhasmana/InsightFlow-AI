"""Analytics Agent.

Computes KPIs from the retrieved rows: totals, top/bottom performers,
concentration, and simple anomaly flags.
"""
from __future__ import annotations

from statistics import mean, pstdev

from .constants import TIME_DIMENSIONS
from .state import PipelineState


def _value_key(rows: list[dict]) -> str | None:
    if not rows:
        return None
    numeric = [k for k, v in rows[0].items() if isinstance(v, (int, float))]
    return numeric[0] if numeric else None


def _label_key(rows: list[dict]) -> str | None:
    if not rows:
        return None
    for k, v in rows[0].items():
        if isinstance(v, str):
            return k
    return None


def run(state: PipelineState) -> PipelineState:
    rows = state.get("rows", [])
    metric = state["intent"]["metric"]
    kpis: dict = {"metric": metric}

    value_key = _value_key(rows)
    label_key = _label_key(rows)

    if not rows or value_key is None:
        state["kpis"] = {"metric": metric, "total": 0, "note": "No data for this question."}
        return state

    values = [float(r[value_key]) for r in rows]
    total = round(sum(values), 2)
    kpis["total"] = total
    kpis["value_key"] = value_key

    if label_key and len(rows) >= 2:
        ranked = sorted(rows, key=lambda r: float(r[value_key]), reverse=True)
        top = ranked[0]
        bottom = ranked[-1]
        kpis["top"] = {"name": top[label_key], "value": round(float(top[value_key]), 2)}
        kpis["bottom"] = {"name": bottom[label_key], "value": round(float(bottom[value_key]), 2)}
        # Share of total is meaningless for a ratio metric like margin.
        if metric != "margin":
            kpis["top_share_pct"] = round(float(top[value_key]) / total * 100, 1) if total else 0

    if len(values) >= 2:
        avg = mean(values)
        sd = pstdev(values)
        kpis["average"] = round(avg, 2)
        anomalies = []
        if sd > 0 and label_key:
            for r in rows:
                z = (float(r[value_key]) - avg) / sd
                if abs(z) >= 2:
                    anomalies.append({"name": r[label_key], "value": round(float(r[value_key]), 2), "z_score": round(z, 2)})
        kpis["anomalies"] = anomalies

        # Growth for time-series (chronologically ordered) dimensions.
        if state["intent"].get("dimension") in TIME_DIMENSIONS and values[0] != 0:
            growth = (values[-1] - values[0]) / abs(values[0]) * 100
            kpis["period_growth_pct"] = round(growth, 1)
            mom = [
                round((values[i] - values[i - 1]) / abs(values[i - 1]) * 100, 1)
                for i in range(1, len(values))
                if values[i - 1] != 0
            ]
            if mom:
                kpis["avg_mom_growth_pct"] = round(mean(mom), 1)

    # Summing percentages across groups is meaningless; average is the headline.
    if metric == "margin" and len(values) > 1:
        kpis.pop("total", None)

    state["kpis"] = kpis
    return state
