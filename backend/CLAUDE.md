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
│   ├── agents.py    # 2 active CrewAI agents: financial_data_analyst (stock/ETF ranking),
│   │                #   investment_advisor (chat synthesis). Both tools=[], max_iter=2.
│   ├── tasks.py     # Task factory — embeds prefetched JSON in description; output_pydantic
│   ├── output_models.py  # Pydantic models for crew outputs (SectorRankingOutput, etc.)
│   └── tools/       # sector_analysis (SectorPerformanceTool, SectorStocksMapperTool),
│                    #   market_research tools (web search, news, sentiment)
├── services/
│   ├── chat_service.py           # Prefetches snapshot+news, then runs chat crew
│   ├── recommendations_service.py # Prefetches sector stocks/ETFs, runs per-sector crews
│   ├── crew_runner.py            # Subprocess-based crew execution with hard timeout/kill
│   ├── data_fetchers.py          # Pure-Python yfinance fetchers (no LLM)
│   ├── crew_service.py           # Thin facade (backward compat only)
│   ├── job_store.py              # Redis-backed async job tracking
│   ├── cache.py                  # Redis TTL cache
│   └── intent_classifier.py      # OpenRouter JSON-mode intent classifier (singleton)
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

**Pre-fetch + crew pattern:**
Data is fetched synchronously in Python (via `data_fetchers.py`) before the crew runs.
The crew receives everything it needs in the task description as a JSON block — agents
call no tools. This avoids rate-limit failures on free-tier models.

**Intent-driven chat:**
`classify_intent(message)` uses `INTENT_MODEL_NAME` (fast small model) to decide whether
`needs_news` is true. If so, news is prefetched via `fetch_stock_news_sync` before the
chat crew runs.

**Service split:**
- `ChatService` — owns the chat crew flow
- `RecommendationsService` — owns stock AND fund flows (fund uses `identify_top_etfs_in_sector`, completely separate from stock)
- `CrewService` — legacy facade, delegates to the above two

## Environment Variables (.env)

```
LLM_PROVIDER=openrouter                       # openrouter | openai | groq
OPENROUTER_API_KEY=sk-or-...                  # Required for OpenRouter LLM + intent classifier
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1  # Default, can override
LLM_MODEL_NAME=google/gemma-4-31b-it:free  # Main crew model on OpenRouter
INTENT_MODEL_NAME=meta-llama/llama-3.2-3b-instruct:free  # Fast model for intent classification
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


## Key Points:
- Never read paths like venv/ or node_modules/