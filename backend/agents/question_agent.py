"""Question Understanding Agent.

Determines the intent, target metric, grouping dimension, and time period of a
natural-language business question. Uses the LLM when available, otherwise a
keyword heuristic.
"""
from __future__ import annotations

from ..llm import llm
from .state import PipelineState

METRICS = {
    "revenue": ["revenue", "sales", "income", "turnover", "top line"],
    "profit": ["profit", "margin", "earnings", "bottom line"],
    "quantity": ["units", "quantity", "volume", "orders sold"],
    "orders": ["orders", "transactions", "deals"],
    "aov": ["average order", "aov", "basket size"],
}
DIMENSIONS = {
    "region": ["region", "geography", "market", "territory"],
    "category": ["category", "product type"],
    "product": ["product", "sku", "item"],
    "segment": ["segment", "customer type", "tier"],
    "quarter": ["quarter", "quarterly", "by quarter", "qoq", "q/q"],
    "month": ["month", "monthly", "trend", "over time", "by month"],
}
PERIODS = {
    "last_quarter": ["last quarter", "past quarter", "q1", "q2", "q3", "q4"],
    "last_month": ["last month", "past month"],
    "last_year": ["last year", "past year", "ytd", "year to date"],
    "last_30_days": ["last 30 days", "past 30 days", "last month"],
}

SYSTEM = (
    "You are an intent parser for a business intelligence system. "
    "Return JSON with keys: metric (revenue|profit|quantity|orders|aov), "
    "dimension (region|category|product|segment|quarter|month|null), "
    "time_period (last_month|last_quarter|last_year|all_time), "
    "intent_type (aggregate|trend|comparison|ranking). "
    "Use dimension 'quarter' when the user asks for quarterly figures, and "
    "'month' for monthly or over-time trends."
)


def _heuristic(question: str) -> dict:
    q = question.lower()

    def match(mapping: dict, default):
        for key, words in mapping.items():
            if any(w in q for w in words):
                return key
        return default

    metric = match(METRICS, "revenue")
    dimension = match(DIMENSIONS, None)
    period = match(PERIODS, "all_time")

    if any(w in q for w in ["trend", "over time", "monthly", "by month", "growth"]):
        intent_type = "trend"
        if dimension not in ("month", "quarter"):
            dimension = "month"
    elif any(w in q for w in ["top", "best", "worst", "rank", "highest", "lowest"]):
        intent_type = "ranking"
    elif dimension in ("month", "quarter"):
        intent_type = "trend"
    elif dimension:
        intent_type = "comparison"
    else:
        intent_type = "aggregate"

    return {
        "metric": metric,
        "dimension": dimension,
        "time_period": period,
        "intent_type": intent_type,
    }


def run(state: PipelineState) -> PipelineState:
    question = state["question"]
    intent = None
    parsed = llm.complete_json(SYSTEM, question)
    if parsed and parsed.get("metric"):
        intent = {
            "metric": parsed.get("metric", "revenue"),
            "dimension": parsed.get("dimension"),
            "time_period": parsed.get("time_period", "all_time"),
            "intent_type": parsed.get("intent_type", "aggregate"),
        }
        if intent["dimension"] in ("null", "none", ""):
            intent["dimension"] = None
    if intent is None:
        intent = _heuristic(question)

    state["intent"] = intent
    state["llm_powered"] = bool(parsed)
    return state
