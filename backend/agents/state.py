"""Shared state passed between agents in the pipeline."""
from __future__ import annotations

from typing import Any, TypedDict


class PipelineState(TypedDict, total=False):
    question: str
    intent: dict[str, Any]
    sql: str
    rows: list[dict[str, Any]]
    kpis: dict[str, Any]
    forecast: dict[str, Any]
    charts: list[dict[str, Any]]
    executive_summary: str
    recommendations: list[str]
    llm_powered: bool
