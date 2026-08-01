"""SQL Agent.

Builds a safe, parameterized query from the parsed intent and executes it. We
deliberately construct queries from a whitelist of metrics/dimensions/time
filters rather than executing free-form LLM SQL, which keeps the system
injection-safe while still being fully driven by the natural-language question.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from sqlalchemy import Float, Integer, String, case, cast, func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Customer, Product, Sale
from .constants import TIME_DIMENSIONS
from .state import PipelineState

_METRIC_LABEL = {
    "revenue": "revenue",
    "profit": "profit",
    "quantity": "units",
    "orders": "orders",
    "aov": "avg_order_value",
    "margin": "margin_pct",
}


def _metric_expr(metric: str):
    if metric == "revenue":
        return func.sum(Sale.revenue)
    if metric == "profit":
        return func.sum(Sale.profit)
    if metric == "quantity":
        return func.sum(Sale.quantity)
    if metric == "orders":
        return func.count(Sale.sale_id)
    if metric == "aov":
        return func.sum(Sale.revenue) / func.cast(func.count(Sale.sale_id), Float)
    if metric == "margin":
        return func.sum(Sale.profit) * 100.0 / func.sum(Sale.revenue)
    return func.sum(Sale.revenue)


# ----------------------------------------------------------------------------
# Time-period resolution: turns a token into (start_inclusive, end_exclusive).
# ----------------------------------------------------------------------------

def _quarter_start(d: date) -> date:
    return date(d.year, ((d.month - 1) // 3) * 3 + 1, 1)


def _fy_bounds(end_year: int, start_month: int) -> tuple[date, date]:
    if start_month == 1:
        return date(end_year, 1, 1), date(end_year + 1, 1, 1)
    return date(end_year - 1, start_month, 1), date(end_year, start_month, 1)


def _resolve_period(token: str | None) -> tuple[date | None, date | None]:
    today = date.today()
    if not token or token == "all_time":
        return None, None

    m = re.fullmatch(r"last_(\d+)_days", token)
    if m:
        return today - timedelta(days=int(m.group(1))), None

    rolling = {
        "last_week": 7,
        "last_month": 30,
        "last_quarter": 90,
        "last_6_months": 182,
        "last_year": 365,
    }
    if token in rolling:
        return today - timedelta(days=rolling[token]), None

    if token == "ytd":
        return date(today.year, 1, 1), None
    if token == "mtd":
        return today.replace(day=1), None
    if token == "qtd":
        return _quarter_start(today), None

    try:
        if token.startswith("month:"):
            y, mo = (int(x) for x in token[6:].split("-"))
            start = date(y, mo, 1)
            end = date(y + 1, 1, 1) if mo == 12 else date(y, mo + 1, 1)
            return start, end
        if token.startswith("year:"):
            y = int(token[5:])
            return date(y, 1, 1), date(y + 1, 1, 1)
        if token.startswith("quarter:"):
            y_s, q_s = token[8:].split("-Q")
            y, q = int(y_s), int(q_s)
            sm = (q - 1) * 3 + 1
            end = date(y + 1, 1, 1) if q == 4 else date(y, sm + 3, 1)
            return date(y, sm, 1), end
        if token.startswith("fy:"):
            return _fy_bounds(int(token[3:]), settings.fiscal_year_start_month)
    except (ValueError, TypeError):
        return None, None

    return None, None


# ----------------------------------------------------------------------------
# Grouping expressions per dimension.
# ----------------------------------------------------------------------------

def _fiscal_year_expr():
    sm = settings.fiscal_year_start_month
    yr = cast(func.strftime("%Y", Sale.date), Integer)
    mo = cast(func.strftime("%m", Sale.date), Integer)
    fy = yr if sm == 1 else case((mo >= sm, yr + 1), else_=yr)
    return func.printf("FY%d", fy).label("fiscal_year")


def _quarter_expr():
    qnum = cast((cast(func.strftime("%m", Sale.date), Integer) + 2) / 3, Integer)
    return func.strftime("%Y", Sale.date).op("||")("-Q").op("||")(cast(qnum, String))


def _dow_name():
    dow = cast(func.strftime("%w", Sale.date), Integer)  # 0=Sun … 6=Sat
    return case(
        (dow == 0, "Sun"), (dow == 1, "Mon"), (dow == 2, "Tue"), (dow == 3, "Wed"),
        (dow == 4, "Thu"), (dow == 5, "Fri"), else_="Sat",
    )


def _dow_order():
    dow = cast(func.strftime("%w", Sale.date), Integer)
    return case((dow == 0, 7), else_=dow)  # Mon=1 … Sun=7


def _current_period_start(dimension: str, today: date) -> date | None:
    if dimension == "month":
        return today.replace(day=1)
    if dimension == "quarter":
        return _quarter_start(today)
    if dimension == "week":
        return today - timedelta(days=today.weekday())
    return None


def _grouping(dimension: str | None):
    """Return (group_expr, join, order_expr) for the dimension, or Nones."""
    if dimension == "region":
        return Sale.region.label("region"), None, None
    if dimension == "category":
        return Product.category.label("category"), (Product, Product.product_id == Sale.product_id), None
    if dimension == "brand":
        return Product.brand.label("brand"), (Product, Product.product_id == Sale.product_id), None
    if dimension == "product":
        return Product.product_name.label("product"), (Product, Product.product_id == Sale.product_id), None
    if dimension == "segment":
        return Customer.segment.label("segment"), (Customer, Customer.customer_id == Sale.customer_id), None
    if dimension == "city":
        return Customer.city.label("city"), (Customer, Customer.customer_id == Sale.customer_id), None
    if dimension == "year":
        col = func.strftime("%Y", Sale.date).label("year")
        return col, None, col
    if dimension == "fiscal_year":
        col = _fiscal_year_expr()
        return col, None, col
    if dimension == "quarter":
        col = _quarter_expr().label("quarter")
        return col, None, col
    if dimension == "month":
        col = func.strftime("%Y-%m", Sale.date).label("month")
        return col, None, col
    if dimension == "week":
        col = func.strftime("%Y-W%W", Sale.date).label("week")
        return col, None, col
    if dimension == "day":
        col = func.strftime("%Y-%m-%d", Sale.date).label("day")
        return col, None, col
    if dimension == "day_of_week":
        return _dow_name().label("day_of_week"), None, _dow_order()
    return None, None, None


def run(state: PipelineState, session: Session) -> PipelineState:
    intent = state["intent"]
    metric = intent["metric"] if intent.get("metric") in _METRIC_LABEL else "revenue"
    dimension = intent.get("dimension")
    start, end = _resolve_period(intent.get("time_period"))

    metric_expr = _metric_expr(metric).label(_METRIC_LABEL[metric])
    group, join, order_expr = _grouping(dimension)

    if group is None:
        stmt = select(metric_expr)
    else:
        stmt = select(group, metric_expr)
        if join is not None:
            stmt = stmt.join(join[0], join[1])
        stmt = stmt.group_by(group)

    if start is not None:
        stmt = stmt.where(Sale.date >= start)
    if end is not None:
        stmt = stmt.where(Sale.date < end)

    # For fine-grained time buckets, drop the current incomplete period so the
    # last point (and any growth/forecast) isn't skewed — unless the user asked
    # for an explicit period (end set).
    if end is None and dimension in ("month", "quarter", "week"):
        cutoff = _current_period_start(dimension, date.today())
        if cutoff is not None:
            stmt = stmt.where(Sale.date < cutoff)

    if group is not None:
        if dimension in TIME_DIMENSIONS or dimension == "day_of_week":
            stmt = stmt.order_by(order_expr)
        else:
            stmt = stmt.order_by(metric_expr.asc() if intent.get("ascending") else metric_expr.desc())
            # Apply a "top N" / "bottom N" limit for ranking questions.
            limit = intent.get("limit")
            if isinstance(limit, int) and limit > 0:
                stmt = stmt.limit(limit)

    result = session.execute(stmt).mappings().all()
    rows = [dict(r) for r in result]
    for row in rows:
        for k, v in row.items():
            if isinstance(v, float):
                row[k] = round(v, 2)

    state["rows"] = rows
    return state
