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


def _money(v) -> str:
    try:
        return f"${float(v):,.0f}"
    except (TypeError, ValueError):
        return str(v)


def _heuristic(state: PipelineState) -> tuple[str, list[str]]:
    intent = state["intent"]
    kpis = state.get("kpis", {})
    forecast = state.get("forecast", {})
    metric = intent["metric"]
    total = kpis.get("total", 0)

    parts = [f"Total {metric} across the selected period is {_money(total)}."]
    recs: list[str] = []

    if "top" in kpis:
        top = kpis["top"]
        share = kpis.get("top_share_pct", 0)
        parts.append(f"{top['name']} leads with {_money(top['value'])} ({share}% of the total).")
        if share >= 40:
            recs.append(
                f"Reduce concentration risk: {top['name']} drives {share}% of {metric}. "
                f"Diversify by investing in underperformers like {kpis.get('bottom', {}).get('name', 'lagging segments')}."
            )
        else:
            recs.append(f"Double down on {top['name']} — it is the strongest performer and has room to scale.")

    if "bottom" in kpis:
        bottom = kpis["bottom"]
        parts.append(f"{bottom['name']} is the weakest at {_money(bottom['value'])}.")
        recs.append(f"Investigate {bottom['name']}: run a targeted campaign or review pricing to lift performance.")

    if kpis.get("anomalies"):
        names = ", ".join(a["name"] for a in kpis["anomalies"])
        parts.append(f"Statistical anomalies detected in: {names}.")
        recs.append(f"Audit {names} for data quality issues or genuine outlier events before acting on them.")

    if forecast.get("available"):
        direction = forecast["direction"]
        nxt = forecast["next_value"]
        parts.append(f"The near-term forecast trends {direction}, with the next period projected at {_money(nxt)}.")
        if direction == "down":
            recs.append("Forecast is declining — accelerate pipeline and retention initiatives now to reverse the trend.")
        elif direction == "up":
            recs.append("Momentum is positive — secure inventory and capacity to capture the projected upside.")

    if "period_growth_pct" in kpis:
        parts.append(f"Growth over the period is {kpis['period_growth_pct']}%.")

    if not recs:
        recs.append("Maintain current strategy and set up KPI monitoring to catch changes early.")

    return " ".join(parts), recs[:4]


def run(state: PipelineState) -> PipelineState:
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
