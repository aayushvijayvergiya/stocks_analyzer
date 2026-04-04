# CLAUDE.md — backend

FastAPI + CrewAI backend for real-time stock and fund analysis. Python 3.12.

## Commands

```bash
# Activate venv
.venv/Scripts/Activate.ps1          # PowerShell
source .venv/Scripts/activate        # bash

# Run server
uvicorn app.main:app --reload

# Run unit tests (no server needed)
python -m pytest tests/test_job_store.py tests/test_output_models.py tests/test_crew_service.py tests/test_chat_service.py tests/test_recommendations_service.py -v

# Run all unit tests
python -m pytest tests/ -v --ignore=tests/test_chat.py --ignore=tests/test_stocks.py --ignore=tests/test_funds.py

# Integration tests (require running server + Redis)
python -m pytest tests/test_chat.py tests/test_stocks.py tests/test_funds.py -v

# Install dependencies
uv sync
```

## Architecture

```
app/
├── api/v1/          # FastAPI routers (chat, stocks, funds)
├── crew/
│   ├── agents.py    # 4 CrewAI agents (market_researcher, financial_data_analyst,
│   │                #   sector_performance_analyst, investment_advisor)
│   ├── tasks.py     # Task factory with output_pydantic on structured tasks
│   ├── output_models.py  # Pydantic models for crew outputs (SectorRankingOutput, etc.)
│   └── tools/       # yfinance, web search, sector analysis, news tools
├── services/
│   ├── chat_service.py           # Intent-driven chat crew execution
│   ├── recommendations_service.py # Stock + fund recommendation crews (separate flows)
│   ├── crew_service.py           # Thin facade (backward compat only)
│   ├── job_store.py              # Redis-backed async job tracking
│   ├── cache.py                  # Redis TTL cache
│   └── intent_classifier.py      # Groq JSON-mode intent classifier (singleton client)
├── models/
│   ├── requests.py   # ChatRequest, StockRecommendationParams, Source, etc.
│   └── responses.py  # ChatResponse, JobStatus, StockRecommendationResponse, etc.
├── config.py         # Pydantic Settings (reads .env)
├── dependencies.py   # FastAPI DI: Redis, CacheService, JobStore, CrewService
└── main.py           # App entry, lifespan, CORS, health check
```

## Key Patterns

**Async job pattern (stocks/funds):**
`POST /recommendations` → returns `job_id` immediately → background crew runs → `GET /recommendations/{job_id}` polls for result.

**Structured crew output:**
Tasks use `output_pydantic=<Model>` so agents return validated Pydantic objects. Access via `result.pydantic` (never `str(result)`).

**Intent-driven chat:**
`classify_intent(message)` uses OpenRouter (`LLM_MODEL_NAME` from env) to decide which tasks to run: `needs_news` → `research_stock_news`, `needs_metrics` → `analyze_stock_financials`, neither → default to financials.

**Service split:**
- `ChatService` — owns the chat crew flow
- `RecommendationsService` — owns stock AND fund flows (fund uses `identify_top_etfs_in_sector`, completely separate from stock)
- `CrewService` — legacy facade, delegates to the above two

## Environment Variables (.env)

```
LLM_PROVIDER=openrouter                       # openrouter | openai | groq
OPENROUTER_API_KEY=sk-or-...                  # Required for OpenRouter LLM + intent classifier
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1  # Default, can override
LLM_MODEL_NAME=meta-llama/llama-4-scout:free  # Any model available on OpenRouter
OPENAI_API_KEY=sk-...                         # Optional fallback if LLM_PROVIDER=openai
NEWS_API_KEY=...                              # Optional (NewsAPI fallback)
SERPER_API_KEY=...                            # Optional (better web search)
REDIS_URL=redis://localhost:6379
```

## Testing

- **Unit tests** — mock Redis and CrewAI crew; no server needed; always runnable
- **Integration tests** — `test_chat.py`, `test_stocks.py`, `test_funds.py` hit real endpoints; require `uvicorn` + Redis running
- `asyncio_mode = "auto"` is set in `pyproject.toml` — do NOT add `@pytest.mark.asyncio` decorators

## Documentation Conventions

- Code reviews → `../docs/reviews/<desc>_review.md`
- Development plans → `../docs/plan/<desc>_plan.md`
- Design specs → `../docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`
