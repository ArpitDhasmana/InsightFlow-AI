"""Question Understanding Agent.

Determines the metric, grouping dimension, time period, and intent type of a
natural-language business question. Uses the LLM when available, otherwise a
keyword + pattern heuristic. Both paths emit the same intent shape so the SQL
agent can build a query deterministically.
"""
from __future__ import annotations

import re
from datetime import date

from ..llm import llm
from .constants import TIME_DIMENSIONS
from .state import PipelineState

# Ordered by priority — the first mapping whose keyword appears wins.
METRICS = {
    "margin": ["profit margin", "margin", "profitability"],
    "aov": ["average order", "aov", "basket size", "average sale value"],
    "orders": ["orders", "transactions", "deals", "number of sales"],
    "quantity": ["units sold", "units", "quantity", "volume"],
    "profit": ["profit", "earnings", "bottom line"],
    "revenue": ["revenue", "sales", "income", "turnover", "top line"],
}

DIMENSIONS = {
    "day_of_week": ["day of week", "day of the week", "weekday", "which day", "busiest day"],
    "fiscal_year": ["fiscal", "financial year"],
    "region": ["region", "geography", "market", "territory"],
    "category": ["category", "product type"],
    "brand": ["brand"],
    "product": ["product", "sku", "item"],
    "segment": ["segment", "customer type", "tier"],
    "city": ["city", "cities"],
    "quarter": ["quarter", "quarterly", "qoq"],
    "week": ["weekly", "week", "wow"],
    "day": ["daily", "day-wise", "day wise", "by day", "per day", "each day"],
    "month": ["monthly", "month", "over time", "by month"],
    "year": ["yearly", "annually", "annual", "year over year", "yoy", "by year", "per year"],
}

MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9, "october": 10,
    "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}

SYSTEM = (
    "You are an intent parser for a business intelligence system over a sales "
    "database. Return JSON with keys: \n"
    "- metric: one of revenue|profit|quantity|orders|aov|margin\n"
    "- dimension: how to group results, one of region|category|brand|product|"
    "segment|city|year|fiscal_year|quarter|month|week|day|day_of_week|null\n"
    "- time_period: a token describing the date filter. Use 'all_time' for no "
    "filter; relative tokens last_week|last_month|last_quarter|last_6_months|"
    "last_year|last_30_days|ytd|mtd|qtd; or a concrete token 'month:YYYY-MM', "
    "'year:YYYY', 'quarter:YYYY-Qn', 'fy:YYYY'.\n"
    "- intent_type: aggregate|trend|comparison|ranking\n"
    "- limit: for 'top N' / 'bottom N' questions, the integer N; otherwise null\n"
    "Rules: use dimension 'day' for day-by-day within a month (also set "
    "time_period to that month), 'year' for yearly, 'fiscal_year' for financial "
    "years, 'week' for weekly, 'day_of_week' for weekday patterns. A specific "
    "period like 'in 2025' is a time_period (year:2025), not a dimension. "
    "Treat 'FY', 'FY25', 'fiscal year', 'financial year' as dimension "
    "fiscal_year when comparing or trending fiscal years; use time_period "
    "'fy:YYYY' only to filter to one specific fiscal year. "
    "Examples: 'daily revenue in January 2026' -> {metric:revenue,dimension:day,"
    "time_period:month:2026-01,intent_type:trend}. 'revenue by brand' -> "
    "{metric:revenue,dimension:brand,time_period:all_time,intent_type:comparison}. "
    "'fy26 and 25 trends' -> {metric:revenue,dimension:fiscal_year,"
    "time_period:all_time,intent_type:trend}."
)


def _match(mapping: dict, q: str, default=None):
    for key, words in mapping.items():
        if any(w in q for w in words):
            return key
    return default


def _parse_time(q: str) -> str:
    today = date.today()
    year_m = re.search(r"\b(20\d{2})\b", q)
    year = int(year_m.group(1)) if year_m else None

    if "year to date" in q or "ytd" in q:
        return "ytd"
    if "month to date" in q or "mtd" in q:
        return "mtd"
    if "quarter to date" in q or "qtd" in q:
        return "qtd"

    m = re.search(r"(?:last|past)\s+(\d+)\s+days", q)
    if m:
        return f"last_{int(m.group(1))}_days"
    if any(p in q for p in ("last 6 months", "past 6 months", "last six months")):
        return "last_6_months"
    if "last week" in q or "past week" in q:
        return "last_week"
    if "last month" in q or "past month" in q:
        return "last_month"
    if "last quarter" in q or "past quarter" in q:
        return "last_quarter"
    if "last year" in q or "past year" in q:
        return "last_year"

    fy = re.search(r"\bfy\s?(20\d{2})\b", q)
    if fy:
        return f"fy:{fy.group(1)}"
    if ("fiscal" in q or "financial year" in q) and year:
        return f"fy:{year}"

    qm = re.search(r"\bq([1-4])\b", q)
    if qm:
        return f"quarter:{year or today.year}-Q{qm.group(1)}"

    for name, num in MONTHS.items():
        # 'may' is also a common modal verb; only treat it as a month with a year.
        if name == "may" and year is None:
            continue
        if re.search(rf"\b{name}\b", q):
            return f"month:{year or today.year:04d}-{num:02d}"

    if year:
        return f"year:{year}"
    return "all_time"


def _heuristic(question: str) -> dict:
    q = question.lower()
    metric = _match(METRICS, q, "revenue")
    dimension = _match(DIMENSIONS, q, None)
    time_period = _parse_time(q)

    # 'fy', 'fy25', 'fiscal year' etc. describe the fiscal-year dimension.
    if "fiscal" in q or "financial year" in q or re.search(r"\bfy\s?\d{2,4}\b", q):
        dimension = "fiscal_year"

    if any(w in q for w in ["top", "best", "worst", "rank", "highest", "lowest", "most", "least"]):
        intent_type = "ranking"
    elif dimension in TIME_DIMENSIONS:
        intent_type = "trend"
    elif any(w in q for w in ["trend", "over time", "growth"]):
        intent_type = "trend"
        if dimension is None:
            dimension = "month"
    elif dimension:
        intent_type = "comparison"
    else:
        intent_type = "aggregate"

    limit_m = re.search(r"\b(?:top|bottom|first)\s+(\d+)\b", q)
    limit = int(limit_m.group(1)) if limit_m else None

    return {
        "metric": metric,
        "dimension": dimension,
        "time_period": time_period,
        "intent_type": intent_type,
        "limit": limit,
    }


def run(state: PipelineState) -> PipelineState:
    question = state["question"]
    parsed = llm.complete_json(SYSTEM, question)
    intent = None
    if parsed and parsed.get("metric"):
        dim = parsed.get("dimension")
        if dim in ("null", "none", ""):
            dim = None
        intent = {
            "metric": parsed.get("metric", "revenue"),
            "dimension": dim,
            "time_period": parsed.get("time_period") or "all_time",
            "intent_type": parsed.get("intent_type", "aggregate"),
            "limit": parsed.get("limit") if isinstance(parsed.get("limit"), int) else None,
        }
    if intent is None:
        intent = _heuristic(question)

    # 'bottom / lowest / worst' questions should surface the smallest values.
    intent["ascending"] = any(
        w in question.lower() for w in ["bottom", "worst", "lowest", "least", "smallest", "fewest"]
    )

    state["intent"] = intent
    state["llm_powered"] = bool(parsed)
    return state
