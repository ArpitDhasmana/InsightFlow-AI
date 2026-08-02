"""Executive Agent.

Turns the analytics + forecast into an executive summary and a set of concrete
recommendations. Uses the LLM when available for polished narrative, otherwise
generates a structured summary from the computed KPIs.
"""
from __future__ import annotations

import json

from ..llm import llm
from .state import PipelineState

SYSTEM = (
    "You are an executive business advisor. Given a question and computed "
    "analytics, write a concise executive summary (3-4 sentences) and 3 concrete, "
    "action-oriented recommendations. Return JSON with keys 'summary' (string) and "
    "'recommendations' (array of strings). Be specific and reference the numbers."
)


def _fmt(metric: str, v) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    if metric == "margin":
        return f"{x:.1f}%"
    if metric in ("quantity", "orders"):
        return f"{x:,.0f}"
    return f"${x:,.0f}"


def _heuristic(state: PipelineState) -> tuple[str, list[str]]:
    intent = state["intent"]
    kpis = state.get("kpis", {})
    forecast = state.get("forecast", {})
    metric = intent["metric"]
    is_margin = metric == "margin"
    total = kpis.get("total")

    # Two-dimensional pivot: a simple comparison narrative.
    if intent.get("breakdown"):
        dim = intent["dimension"].replace("_", " ")
        bd = intent["breakdown"].replace("_", " ")
        summary = (
            f"Comparing {metric} by {dim} across each {bd}. "
            f"Total {metric} over the selected scope is {_fmt(metric, total or 0)}. "
            f"Use the chart to spot which {dim} is gaining or losing share over time."
        )
        return summary, [
            f"Watch for a {dim} whose {metric} is trending down across {bd}s and address it early.",
            f"Double down on the {dim} showing the strongest, most consistent growth.",
        ]

    parts: list[str] = []
    if is_margin:
        headline = kpis.get("average", total)
        if headline is not None:
            prefix = "The average profit margin" if "average" in kpis else "The overall profit margin"
            parts.append(f"{prefix} is {_fmt(metric, headline)}.")
    else:
        parts.append(f"Total {metric} across the selected period is {_fmt(metric, total or 0)}.")

    recs: list[str] = []

    if "top" in kpis:
        top = kpis["top"]
        if is_margin:
            parts.append(f"{top['name']} has the highest margin at {_fmt(metric, top['value'])}.")
            recs.append(f"Study what makes {top['name']} so profitable and apply those levers elsewhere.")
        else:
            share = kpis.get("top_share_pct", 0)
            parts.append(f"{top['name']} leads with {_fmt(metric, top['value'])} ({share}% of the total).")
            if share >= 40:
                recs.append(
                    f"Reduce concentration risk: {top['name']} drives {share}% of {metric}. "
                    f"Diversify by investing in underperformers like {kpis.get('bottom', {}).get('name', 'lagging segments')}."
                )
            else:
                recs.append(f"Double down on {top['name']} — it is the strongest performer and has room to scale.")

    if "bottom" in kpis:
        bottom = kpis["bottom"]
        descriptor = "the thinnest margin" if is_margin else "the weakest"
        parts.append(f"{bottom['name']} has {descriptor} at {_fmt(metric, bottom['value'])}.")
        recs.append(f"Investigate {bottom['name']}: review pricing, cost, or mix to lift performance.")

    if kpis.get("anomalies"):
        names = ", ".join(a["name"] for a in kpis["anomalies"])
        parts.append(f"Statistical anomalies detected in: {names}.")
        recs.append(f"Audit {names} for data quality issues or genuine outlier events before acting on them.")

    if forecast.get("available"):
        direction = forecast["direction"]
        nxt = forecast["next_value"]
        parts.append(f"The near-term forecast trends {direction}, with the next period projected at {_fmt(metric, nxt)}.")
        if direction == "down":
            recs.append("Forecast is declining — accelerate pipeline and retention initiatives now to reverse the trend.")
        elif direction == "up":
            recs.append("Momentum is positive — secure inventory and capacity to capture the projected upside.")

    if "period_growth_pct" in kpis:
        parts.append(f"Change over the period is {kpis['period_growth_pct']}%.")

    if not recs:
        recs.append("Maintain current strategy and set up KPI monitoring to catch changes early.")

    return " ".join(parts), recs[:4]


def run(state: PipelineState) -> PipelineState:
    # Pivots are summarized deterministically (the LLM only sees a single total).
    if state["intent"].get("breakdown"):
        summary, recs = _heuristic(state)
        state["executive_summary"] = summary
        state["recommendations"] = recs
        return state

    payload = {
        "question": state["question"],
        "intent": state["intent"],
        "kpis": state.get("kpis", {}),
        "forecast": state.get("forecast", {}),
    }
    parsed = llm.complete_json(SYSTEM, json.dumps(payload, default=str))
    if parsed and parsed.get("summary"):
        state["executive_summary"] = parsed["summary"]
        recs = parsed.get("recommendations") or []
        state["recommendations"] = [str(r) for r in recs][:4]
        state["llm_powered"] = True
    else:
        summary, recs = _heuristic(state)
        state["executive_summary"] = summary
        state["recommendations"] = recs
    return state
