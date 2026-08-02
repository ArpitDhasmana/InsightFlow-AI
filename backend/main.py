"""InsightFlow AI — FastAPI application."""
from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from .agents.orchestrator import run_pipeline
from .config import settings
from .database import engine, get_session
from .schemas import AskRequest, AskResponse

app = FastAPI(
    title="InsightFlow AI",
    description="Autonomous Business Intelligence & Executive Intelligence Platform",
    version="1.0.0",
)

_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.on_event("startup")
def _seed_if_empty() -> None:
    """Auto-seed on first boot (e.g. Render's ephemeral disk starts empty)."""
    if "sales" not in inspect(engine).get_table_names():
        from .seed_data import seed

        seed()


@app.get("/health")
def health() -> dict:
    tables = inspect(engine).get_table_names()
    return {
        "status": "ok",
        "database": settings.database_url.split("://")[0],
        "seeded": "sales" in tables,
        "llm_powered": settings.llm_enabled,
    }


@app.post("/api/ask", response_model=AskResponse)
def ask(req: AskRequest, session: Session = Depends(get_session)) -> AskResponse:
    if "sales" not in inspect(engine).get_table_names():
        raise HTTPException(
            status_code=503,
            detail="Database not seeded. Run: python -m backend.seed_data",
        )
    state = run_pipeline(req.question, session)
    return AskResponse(
        question=state["question"],
        intent=state["intent"],
        rows=state.get("rows", []),
        kpis=state.get("kpis", {}),
        forecast=state.get("forecast", {}),
        charts=state.get("charts", []),
        executive_summary=state.get("executive_summary", ""),
        recommendations=state.get("recommendations", []),
        llm_powered=bool(state.get("llm_powered", False)),
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
