"""SQL Agent.

Builds a safe, parameterized query from the parsed intent and executes it. We
deliberately construct queries from a whitelist of metrics/dimensions rather
than executing free-form LLM SQL, which keeps the system injection-safe while
still being fully driven by the natural-language question.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import Float, Integer, String, cast, func, select
from sqlalchemy.orm import Session

from ..models import Customer, Product, Sale
from .state import PipelineState

_METRIC_LABEL = {
    "revenue": "revenue",
    "profit": "profit",
    "quantity": "units",
    "orders": "orders",
    "aov": "avg_order_value",
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
    return func.sum(Sale.revenue)


def _period_start(period: str | None) -> date | None:
    today = date.today()
    if period == "last_month" or period == "last_30_days":
        return today - timedelta(days=30)
    if period == "last_quarter":
        return today - timedelta(days=90)
    if period == "last_year":
        return today - timedelta(days=365)
    return None


def _describe_sql(metric: str, dimension: str | None, start: date | None) -> str:
    agg = {
        "revenue": "SUM(revenue)",
        "profit": "SUM(profit)",
        "quantity": "SUM(quantity)",
        "orders": "COUNT(sale_id)",
        "aov": "SUM(revenue) / COUNT(sale_id)",
    }[metric]
    label = _METRIC_LABEL[metric]
    group_col = {
        "region": "s.region",
        "category": "p.category",
        "product": "p.product_name",
        "segment": "c.segment",
        "month": "strftime('%Y-%m', s.date)",
        "quarter": "strftime('%Y', s.date) || '-Q' || ((strftime('%m', s.date) + 2) / 3)",
    }.get(dimension or "")

    joins = ""
    if dimension in ("category", "product"):
        joins = "\n  JOIN products p ON p.product_id = s.product_id"
    elif dimension == "segment":
        joins = "\n  JOIN customers c ON c.customer_id = s.customer_id"

    where = f"\n  WHERE s.date >= '{start.isoformat()}'" if start else ""
    if group_col:
        order = f"{group_col}" if dimension in ("month", "quarter") else f"{label} DESC"
        return (
            f"SELECT {group_col} AS {dimension}, {agg} AS {label}\n"
            f"  FROM sales s{joins}{where}\n"
            f"  GROUP BY {group_col}\n"
            f"  ORDER BY {order};"
        )
    return f"SELECT {agg} AS {label}\n  FROM sales s{where};"


def run(state: PipelineState, session: Session) -> PipelineState:
    intent = state["intent"]
    metric = intent["metric"]
    dimension = intent.get("dimension")
    start = _period_start(intent.get("time_period"))

    metric_expr = _metric_expr(metric).label(_METRIC_LABEL[metric])
    stmt = select()

    if dimension == "region":
        group = Sale.region.label("region")
        stmt = select(group, metric_expr).group_by(Sale.region)
    elif dimension == "category":
        group = Product.category.label("category")
        stmt = select(group, metric_expr).join(Product, Product.product_id == Sale.product_id).group_by(Product.category)
    elif dimension == "product":
        group = Product.product_name.label("product")
        stmt = select(group, metric_expr).join(Product, Product.product_id == Sale.product_id).group_by(Product.product_name)
    elif dimension == "segment":
        group = Customer.segment.label("segment")
        stmt = select(group, metric_expr).join(Customer, Customer.customer_id == Sale.customer_id).group_by(Customer.segment)
    elif dimension == "month":
        month = func.strftime("%Y-%m", Sale.date).label("month")
        stmt = select(month, metric_expr).group_by(month).order_by(month)
        # Exclude the current, still-incomplete month so trends/growth aren't skewed.
        first_of_month = date.today().replace(day=1)
        stmt = stmt.where(Sale.date < first_of_month)
    elif dimension == "quarter":
        # e.g. '2025-Q2'. (month + 2) / 3 maps months to quarter numbers; the outer
        # cast forces integer truncation (SQLAlchemy's '/' otherwise yields a float).
        qnum = cast((cast(func.strftime("%m", Sale.date), Integer) + 2) / 3, Integer)
        quarter = (
            func.strftime("%Y", Sale.date).op("||")("-Q").op("||")(cast(qnum, String))
        ).label("quarter")
        stmt = select(quarter, metric_expr).group_by(quarter).order_by(quarter)
        # Exclude the current, still-incomplete quarter.
        today = date.today()
        q_start = date(today.year, ((today.month - 1) // 3) * 3 + 1, 1)
        stmt = stmt.where(Sale.date < q_start)
    else:
        stmt = select(metric_expr)

    if start is not None:
        stmt = stmt.where(Sale.date >= start)

    if dimension and dimension not in ("month", "quarter"):
        stmt = stmt.order_by(metric_expr.desc())

    result = session.execute(stmt).mappings().all()
    rows = [dict(r) for r in result]
    # Round numeric values for presentation.
    for row in rows:
        for k, v in row.items():
            if isinstance(v, float):
                row[k] = round(v, 2)

    state["sql"] = _describe_sql(metric, dimension, start)
    state["rows"] = rows
    return state
