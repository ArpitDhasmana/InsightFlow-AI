# InsightFlow AI

**Autonomous Business Intelligence & Executive Intelligence Platform**

InsightFlow AI turns plain-English business questions into executive-level answers.
It chains a set of autonomous agents that understand a question, generate SQL,
retrieve data, compute KPIs, forecast trends, build visualizations, and write an
executive summary with recommended actions.

```
Question → Intent → SQL → Data → Analytics → Forecast → Visualization → Executive Summary → Recommendations
```

## Architecture

```
Frontend Dashboard
        ↓
   FastAPI Backend
        ↓
 LangGraph Orchestrator
        ↓
Question → SQL → Analytics → Forecast → Visualization → Executive
        ↓
   SQL Database (SQLite by default, PostgreSQL via env)
```

## Agents

| Agent | Responsibility |
|-------|----------------|
| **Question** | Detects intent, metrics, entities, and time period |
| **SQL** | Converts the question into SQL and retrieves data |
| **Analytics** | Computes KPIs, growth, margins, and anomalies |
| **Forecast** | Projects future values from historical trends |
| **Visualization** | Produces chart specs (KPI cards, trend lines, bars) |
| **Executive** | Writes the executive summary and recommendations |

The system runs **without any LLM key** using deterministic heuristics, and
automatically upgrades to LLM-powered reasoning when `GEMINI_API_KEY` is set.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Seed the database with demo business data
python -m backend.seed_data

# Run the API
uvicorn backend.main:app --reload
```

Then open http://127.0.0.1:8000/ for the dashboard, or POST to `/api/ask`:

```powershell
curl -X POST http://127.0.0.1:8000/api/ask -H "Content-Type: application/json" -d '{"question":"What was our revenue by region last quarter?"}'
```

## Configuration

Copy `.env.example` to `.env` and adjust:

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `sqlite:///./insightflow.db` | Any SQLAlchemy URL (e.g. PostgreSQL) |
| `GEMINI_API_KEY` | _(empty)_ | Enables LLM-powered agents (Google Gemini) |
| `GEMINI_MODEL` | `gemini-2.5-flash-lite` | Primary Gemini model |
| `GEMINI_FALLBACK_MODEL` | `gemini-2.5-flash` | Used automatically if the primary fails |
| `CORS_ORIGINS` | `*` | Comma-separated allowed browser origins |

## Deployment (Netlify + Render)

The frontend deploys as a static site on **Netlify** and the API as a web
service on **Render**. Netlify proxies `/api/*` and `/health` to Render, so the
browser stays same-origin (no CORS needed).

**Backend — Render**
1. Push this repo to GitHub.
2. In Render: **New +** → **Blueprint** → select the repo. It reads
   [`render.yaml`](render.yaml) and provisions the service.
3. Add the `GEMINI_API_KEY` value in the service's **Environment** tab.
4. Note the service URL, e.g. `https://insightflow-api.onrender.com`.

The database auto-seeds on first boot (Render's free disk is ephemeral, so it
re-seeds on each deploy).

**Frontend — Netlify**
1. In [`netlify.toml`](netlify.toml), replace `INSIGHTFLOW_API_URL` with your
   Render host (e.g. `insightflow-api.onrender.com`).
2. In Netlify: **Add new site** → **Import from Git** → select the repo.
   Publish directory is `frontend` (already set in `netlify.toml`).
3. Deploy. The site calls the backend through the Netlify proxy.

> Not using the proxy? Set `window.__API_BASE__` to the Render URL in
> `frontend/index.html` and set `CORS_ORIGINS` on Render to your Netlify origin.

## Project layout

```
backend/
  main.py            FastAPI app + routes + static frontend
  config.py          Settings loaded from env
  database.py        SQLAlchemy engine/session
  models.py          Sales, Products, Customers, Inventory, Campaigns
  schemas.py         Pydantic request/response models
  seed_data.py       Generates realistic demo data
  llm.py             LLM abstraction with heuristic fallback
  agents/
    state.py         Shared pipeline state
    orchestrator.py  LangGraph pipeline wiring
    question_agent.py
    sql_agent.py
    analytics_agent.py
    forecast_agent.py
    visualization_agent.py
    executive_agent.py
frontend/
  index.html         Single-page dashboard
```
