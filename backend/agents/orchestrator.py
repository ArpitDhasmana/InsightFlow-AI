"""LangGraph Orchestrator.

Wires the six agents into a linear pipeline:

    question -> sql -> analytics -> forecast -> visualization -> executive

LangGraph drives the flow. If LangGraph is unavailable the same nodes run
sequentially so the platform still works.
"""
from __future__ import annotations

from functools import partial

from sqlalchemy.orm import Session

from . import (
    analytics_agent,
    executive_agent,
    forecast_agent,
    question_agent,
    sql_agent,
    visualization_agent,
)
from .state import PipelineState


def _run_sequential(state: PipelineState, session: Session) -> PipelineState:
    state = question_agent.run(state)
    state = sql_agent.run(state, session)
    state = analytics_agent.run(state)
    state = forecast_agent.run(state)
    state = visualization_agent.run(state)
    state = executive_agent.run(state)
    return state


def run_pipeline(question: str, session: Session) -> PipelineState:
    initial: PipelineState = {"question": question}
    try:
        from langgraph.graph import END, START, StateGraph

        graph = StateGraph(PipelineState)
        graph.add_node("question", question_agent.run)
        graph.add_node("sql", partial(sql_agent.run, session=session))
        graph.add_node("analytics", analytics_agent.run)
        graph.add_node("forecast", forecast_agent.run)
        graph.add_node("visualization", visualization_agent.run)
        graph.add_node("executive", executive_agent.run)

        graph.add_edge(START, "question")
        graph.add_edge("question", "sql")
        graph.add_edge("sql", "analytics")
        graph.add_edge("analytics", "forecast")
        graph.add_edge("forecast", "visualization")
        graph.add_edge("visualization", "executive")
        graph.add_edge("executive", END)

        compiled = graph.compile()
        return compiled.invoke(initial)
    except Exception:
        # LangGraph missing or failed — fall back to a direct sequential run.
        return _run_sequential(initial, session)
