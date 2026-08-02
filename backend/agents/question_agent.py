"""Question Understanding Agent.

Determines the metric, grouping dimension, time period, and intent type of a
natural-language business question. Uses the LLM when available, otherwise a
keyword + pattern heuristic. Both paths emit the same intent shape so the SQL
agent can build a query deterministically.
"""
from __future__ import annotations

import calendar
import re
from datetime import date

from ..config import settings
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

_FY_START = settings.fiscal_year_start_month
_FY_START_NAME = calendar.month_name[_FY_START]
_FY_END_NAME = calendar.month_name[12 if _FY_START == 1 else _FY_START - 1]

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
    "- breakdown: an optional SECOND grouping — a TIME dimension (year|"
    "fiscal_year|quarter|month|week|day) to pivot the primary dimension across, "
    "or null. Use it for 'X by <time>' with two groupings, e.g. 'top products by "
    "fiscal year' -> dimension:product, breakdown:fiscal_year.\n"    "Rules: use dimension 'day' for day-by-day within a month (also set "
    "time_period to that month), 'year' for yearly, 'fiscal_year' for financial "
    "years, 'week' for weekly, 'day_of_week' for weekday patterns. A specific "
    "period like 'in 2025' is a time_period (year:2025), not a dimension. "
    "Treat 'FY', 'FY25', 'fiscal year', 'financial year' as dimension "
    "fiscal_year when comparing or trending fiscal years; use time_period "
    "'fy:YYYY' only to filter to one specific fiscal year. "
    f"The fiscal year starts in {_FY_START_NAME}: FYN runs {_FY_START_NAME} "
    f"(N-1) to {_FY_END_NAME} N (e.g. FY2026 = {_FY_START_NAME} 2025 to "
    f"{_FY_END_NAME} 2026). For a specific month named inside a fiscal year, "
    "resolve it to that month's real calendar year and return a 'month:YYYY-MM' "
    "time_period with dimension null. "
    "Examples: 'daily revenue in January 2026' -> {metric:revenue,dimension:day,"
    "time_period:month:2026-01,intent_type:trend}. 'revenue by brand' -> "
    "{metric:revenue,dimension:brand,time_period:all_time,intent_type:comparison}. "
    "'fy26 and 25 trends' -> {metric:revenue,dimension:fiscal_year,"
    "time_period:all_time,intent_type:trend}. "
    "'fy26 july data' -> {metric:revenue,dimension:null,"
    "time_period:month:2025-07,intent_type:aggregate}."
)


def _match(mapping: dict, q: str, default=None):
    for key, words in mapping.items():
        if any(w in q for w in words):
            return key
    return default


def _month_year_in_fy(month_num: int, fy_end_year: int, fy_start_month: int) -> int:
    """Calendar year of a month within a fiscal year labelled by its end year."""
    if fy_start_month == 1:
        return fy_end_year
    return fy_end_year - 1 if month_num >= fy_start_month else fy_end_year


def _parse_time(q: str) -> str:
    today = date.today()
    fy_m = re.search(r"\bfy\s?(\d{2,4})\b", q)
    fy_year = None
    if fy_m:
        n = int(fy_m.group(1))
        fy_year = 2000 + n if n < 100 else n

    year_m = re.search(r"\b(20\d{2})\b", q)
    year = int(year_m.group(1)) if year_m else None
    # A 4-digit year alongside 'fiscal'/'financial year' is the fiscal year.
    if fy_year is None and year and ("fiscal" in q or "financial year" in q):
        fy_year, year = year, None

    if "year to date" in q or "ytd" in q or "this year" in q:
        return "ytd"
    if "month to date" in q or "mtd" in q or "this month" in q:
        return "mtd"
    if "quarter to date" in q or "qtd" in q or "this quarter" in q:
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

    # A named month resolves to a real calendar year — inside a fiscal year if one
    # is given, else an explicit year, else the current year.
    for name, num in MONTHS.items():
        if name == "may" and year is None and fy_year is None:
            continue
        if re.search(rf"\b{name}\b", q):
            if fy_year is not None:
                y = _month_year_in_fy(num, fy_year, settings.fiscal_year_start_month)
            else:
                y = year or today.year
            return f"month:{y:04d}-{num:02d}"

    if fy_year is not None:
        return f"fy:{fy_year}"

    qm = re.search(r"\bq([1-4])\b", q)
    if qm:
        return f"quarter:{year or today.year}-Q{qm.group(1)}"

    if year:
        return f"year:{year}"
    return "all_time"


def _heuristic(question: str) -> dict:
    q = question.lower()
    metric = _match(METRICS, q, "revenue")
    time_period = _parse_time(q)

    # Collect every dimension mentioned so a categorical primary can be paired
    # with a time secondary for a two-dimensional "X by <time>" pivot.
    dims = [k for k, words in DIMENSIONS.items() if any(w in q for w in words)]
    is_fy = "fiscal" in q or "financial year" in q or re.search(r"\bfy\s?\d{2,4}\b", q)
    specific_fy = time_period.startswith("fy:")
    if is_fy and not time_period.startswith("month:"):
        if [d for d in dims if d not in TIME_DIMENSIONS]:
            # e.g. "products by fiscal year" -> pivot; but "products in FY2026" is a filter.
            if not specific_fy:
                dims.append("fiscal_year")
        else:
            wants_series = any(w in q for w in ["trend", "trends", "and", "vs", "versus", "compare", "each", "over"])
            if not (specific_fy and not wants_series):
                dims.append("fiscal_year")
                if specific_fy:
                    time_period = "all_time"

    seen = set()
    dims = [d for d in dims if not (d in seen or seen.add(d))]
    categorical = [d for d in dims if d not in TIME_DIMENSIONS]
    timedims = [d for d in dims if d in TIME_DIMENSIONS]
    if categorical and timedims:
        dimension, breakdown = categorical[0], timedims[0]
    else:
        dimension = dims[0] if dims else None
        breakdown = None

    if any(w in q for w in ["top", "best", "worst", "rank", "highest", "lowest", "most", "least"]):
        intent_type = "ranking"
    elif breakdown or (dimension and dimension not in TIME_DIMENSIONS):
        intent_type = "comparison"
    elif dimension in TIME_DIMENSIONS:
        intent_type = "trend"
    elif any(w in q for w in ["trend", "over time", "growth"]):
        intent_type = "trend"
        if dimension is None:
            dimension = "month"
    else:
        intent_type = "aggregate"

    limit_m = re.search(r"\b(?:top|bottom|first)\s+(\d+)\b", q)
    limit = int(limit_m.group(1)) if limit_m else None

    return {
        "metric": metric,
        "dimension": dimension,
        "breakdown": breakdown,
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
        bd = parsed.get("breakdown")
        if bd in ("null", "none", "") or bd == dim:
            bd = None
        intent = {
            "metric": parsed.get("metric", "revenue"),
            "dimension": dim,
            "breakdown": bd,
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
