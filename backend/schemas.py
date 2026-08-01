"""Pydantic request/response models for the API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, examples=["What was our revenue by region last quarter?"])


class Intent(BaseModel):
    metric: str
    dimension: str | None = None
    time_period: str | None = None
    intent_type: str


class ChartSpec(BaseModel):
    type: str
    title: str
    labels: list[str]
    series: list[dict[str, Any]]


class AskResponse(BaseModel):
    question: str
    intent: Intent
    rows: list[dict[str, Any]]
    kpis: dict[str, Any]
    forecast: dict[str, Any]
    charts: list[ChartSpec]
    executive_summary: str
    recommendations: list[str]
    llm_powered: bool
