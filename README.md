# Stocks Analyzer

An AI-powered stock and fund analysis platform for US and Indian markets. Built with a multi-agent architecture using CrewAI and FastAPI, it provides interactive Q&A, sector-level stock recommendations, and ETF/fund insights — powered by real-time market data.

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128+-green.svg)](https://fastapi.tiangolo.com/)
[![CrewAI](https://img.shields.io/badge/CrewAI-1.7+-orange.svg)](https://crewai.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Repository Structure](#repository-structure)
- [Getting Started](#getting-started)
- [API Reference](#api-reference)
- [Configuration](#configuration)
- [Testing](#testing)
- [Development Guide](#development-guide)
- [Roadmap](#roadmap)
- [Troubleshooting](#troubleshooting)
- [Acknowledgments](#acknowledgments)

---

## Overview

Stocks Analyzer is a full-stack agentic AI application that orchestrates four specialized AI agents to deliver investment insights:

- Ask questions about any stock and get a researched, reasoned answer
- Request top stock picks by sector and receive ranked recommendations with rationale
- Get ETF/fund recommendations across sectors for both US and Indian markets
- All analysis is backed by live market data (yfinance), web search, and news

The backend is production-ready with Redis caching, async job queuing, rate limiting, structured logging, and Docker support. A frontend interface is currently in development.

---

## Features

### AI Agents (CrewAI)

Four specialized agents collaborate in a sequential pipeline:

| Agent | Role |
|---|---|
| **Market Researcher** | Fetches news, trends, and investor sentiment |
| **Financial Data Analyst** | Analyzes price metrics, P/E, EPS, ROE, and valuation |
| **Sector Performance Analyst** | Ranks sectors by performance and identifies opportunities |
| **Investment Advisor** | Synthesizes findings into actionable recommendations |

### Core Capabilities

- **Interactive Stock Chat** — Ask natural-language questions about any stock; intent classification selects the right agents automatically
- **Stock Recommendations** — Top picks by sector with buy rationale, risk assessment, and supporting data
- **Fund/ETF Recommendations** — Top ETFs by sector with performance context
- **Dual Market Support** — US (NYSE, NASDAQ) and India (NSE, BSE)
- **Async Job Processing** — Long-running analyses run in the background; poll for results
- **Redis Caching** — Chat responses cached 5 min, recommendations cached 30 min
- **Rate Limiting** — 100 requests/hour per client
- **Structured Logging** — JSON logs with request IDs throughout

---

## Architecture

```
┌────────────────────────────────────────────────────────┐
│                        Client                          │
│              (Frontend — coming soon)                  │
└───────────────────────┬────────────────────────────────┘
                        │ HTTP
┌───────────────────────▼────────────────────────────────┐
│                    FastAPI App                         │
│  /api/v1/chat   /api/v1/stocks   /api/v1/funds         │
└──────────┬────────────┬──────────────────┬─────────────┘
           │            │                  │
    ┌──────▼──────┐ ┌───▼──────┐    ┌──────▼──────┐
    │ ChatService │ │  Recomm- │    │  CacheService│
    │             │ │  endations│    │  & JobStore  │
    └──────┬──────┘ │  Service │    └──────┬───────┘
           │        └────┬─────┘           │
           │             │                 │
    ┌──────▼─────────────▼─────────┐  ┌───▼────┐
    │         CrewAI Agents        │  │ Redis  │
    │  Market Researcher           │  └────────┘
    │  Financial Data Analyst      │
    │  Sector Performance Analyst  │
    │  Investment Advisor          │
    └──────────────┬───────────────┘
                   │
    ┌──────────────▼───────────────┐
    │           Tools              │
    │  yfinance  │  DuckDuckGo     │
    │  NewsAPI   │  Serper         │
    │  Sector Analysis             │
    └──────────────────────────────┘
```

### Request Flows

**Chat (synchronous):**
```
POST /chat → intent classifier → select tasks → run crew → return response
```

**Recommendations (async job):**
```
POST /recommendations → create job_id → background crew → Redis job store
GET  /recommendations/{job_id} → poll status → return result when complete
```

---

## Repository Structure

```
stocks_analyzer/
├── backend/                    # FastAPI + CrewAI application
│   ├── app/
│   │   ├── api/v1/             # REST API routers
│   │   │   ├── chat.py         # POST /chat
│   │   │   ├── stocks.py       # POST/GET /stocks/recommendations
│   │   │   ├── funds.py        # POST/GET /funds/recommendations
│   │   │   └── router.py       # Router aggregation
│   │   ├── crew/               # Agent definitions and tools
│   │   │   ├── agents.py       # 4 CrewAI agents
│   │   │   ├── tasks.py        # Task factory (structured Pydantic output)
│   │   │   ├── output_models.py# Pydantic models for crew outputs
│   │   │   └── tools/
│   │   │       ├── financial_data.py    # YFinanceDataTool, PortfolioDataTool
│   │   │       ├── market_research.py   # WebSearchTool, NewsAPITool, SentimentTool
│   │   │       └── sector_analysis.py   # SectorPerformanceTool, SectorStocksMapperTool
│   │   ├── services/           # Business logic
│   │   │   ├── chat_service.py           # Intent-driven chat crew execution
│   │   │   ├── recommendations_service.py# Stock & fund recommendation flows
│   │   │   ├── crew_service.py           # Legacy facade (backward compat)
│   │   │   ├── cache.py                  # Redis TTL cache
│   │   │   ├── job_store.py              # Redis-backed async job tracking
│   │   │   └── intent_classifier.py      # Groq JSON-mode intent classification
│   │   ├── models/             # Pydantic request/response models
│   │   │   ├── requests.py
│   │   │   └── responses.py
│   │   ├── utils/              # Logging, exceptions, validators
│   │   ├── config.py           # Pydantic Settings (loads .env)
│   │   ├── dependencies.py     # FastAPI dependency injection
│   │   └── main.py             # App entry point, middleware, lifespan
│   ├── tests/                  # Unit and integration tests
│   ├── knowledge/              # CrewAI knowledge files
│   ├── docker-compose.yml      # Redis + API orchestration
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── requirements.txt
│   └── .env.example
├── docs/
│   ├── plan/                   # Implementation plans
│   └── superpowers/specs/      # Design specifications
└── README.md                   # This file
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Docker (for Redis, or install Redis locally)
- A **Groq API key** (free) — [console.groq.com/keys](https://console.groq.com/keys)
- Optional: OpenAI API key as fallback LLM provider

### Local Development

```bash
# 1. Clone and enter the backend directory
cd backend

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/Scripts/activate      # bash on Windows
# .venv/Scripts/Activate.ps1       # PowerShell

# 3. Install dependencies
pip install uv
uv sync
# OR: pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — set at minimum: GROQ_API_KEY and REDIS_URL

# 5. Start Redis
docker run -d -p 6379:6379 redis:7-alpine

# 6. Start the API server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API is now available at:
- **API root**: http://localhost:8000
- **Interactive docs**: http://localhost:8000/docs
- **OpenAPI schema**: http://localhost:8000/openapi.json
- **Health check**: http://localhost:8000/health

### Docker (Full Stack)

```bash
cd backend
docker-compose up -d
```

This starts both Redis and the FastAPI app. The API is available on port 8000.

---

## API Reference

All endpoints are under `/api/v1/`.

### Health

```
GET /health
```

Returns Redis connectivity and service status.

```json
{
  "status": "healthy",
  "environment": "development",
  "version": "1.0.0",
  "redis_status": "connected",
  "timestamp": "2026-04-03T10:00:00"
}
```

---

### Chat

```
POST /api/v1/chat
```

Ask a natural-language question about a specific stock. The intent classifier determines whether to fetch news, financial metrics, or both.

**Request:**
```json
{
  "message": "What's the current price and recent news for Apple?",
  "stock_symbol": "AAPL",
  "market": "US"
}
```

**Response:**
```json
{
  "response": "Apple Inc. (AAPL) is currently trading at $175.50...",
  "stock_symbol": "AAPL",
  "sources": ["yfinance", "web_search"],
  "agent_reasoning": {
    "intent": { "needs_news": true, "needs_metrics": true },
    "tasks_run": ["research_stock_news", "analyze_stock_financials"]
  },
  "timestamp": "2026-04-03T10:00:00"
}
```

- Cached for **5 minutes**
- Rate limited to **100 requests/hour**
- Indian stocks: use symbols like `RELIANCE` or `TCS` — `.NS` suffix is added automatically

---

### Stock Recommendations

**Create job:**
```
POST /api/v1/stocks/recommendations
```

```json
{
  "timeframe": "30d",
  "market": "US",
  "risk_profile": "moderate"
}
```

Returns immediately with a `job_id`:

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "generated_at": "2026-04-03T10:00:00"
}
```

**Poll for results:**
```
GET /api/v1/stocks/recommendations/{job_id}
```

```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "result": {
    "top_sectors": [
      {
        "sector": "Technology",
        "rank": 1,
        "stocks": [
          {
            "symbol": "AAPL",
            "company_name": "Apple Inc.",
            "recommendation": "BUY",
            "rationale": "Strong fundamentals, growing services revenue...",
            "risk_level": "LOW",
            "current_price": 175.5
          }
        ]
      }
    ],
    "analysis_timestamp": "2026-04-03T10:05:00"
  },
  "created_at": "2026-04-03T10:00:00",
  "completed_at": "2026-04-03T10:05:00"
}
```

- Results cached for **30 minutes**
- Job status values: `pending` → `processing` → `completed` | `failed`
- Jobs auto-expire from Redis after **1 hour**

---

### Fund/ETF Recommendations

Same async pattern as stock recommendations.

**Create job:**
```
POST /api/v1/funds/recommendations
```

```json
{
  "timeframe": "90d",
  "market": "US",
  "risk_profile": "aggressive",
  "fund_type": "equity"
}
```

**Poll:**
```
GET /api/v1/funds/recommendations/{job_id}
```

---

### Supported Parameters

| Parameter | Values | Description |
|---|---|---|
| `market` | `US`, `IN` | Exchange market |
| `timeframe` | `7d`, `30d`, `90d` | Analysis window |
| `risk_profile` | `conservative`, `moderate`, `aggressive` | Risk tolerance |
| `fund_type` | `equity`, `debt`, `balanced` | Fund category (funds only) |

---

## Configuration

Copy `backend/.env.example` to `backend/.env` and configure:

```bash
# ── LLM Provider ──────────────────────────────────────────
LLM_PROVIDER=groq                    # groq (recommended, free) | openai
GROQ_API_KEY=gsk_...                 # Get free at console.groq.com/keys
GROQ_MODEL=llama-3.3-70b-versatile   # Model for main agents
OPENAI_API_KEY=sk-...                # Optional fallback
OPENAI_MODEL=gpt-4o-mini

# ── Redis ─────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379

# ── Cache TTL (seconds) ───────────────────────────────────
CACHE_TTL_STOCKS=1800                # 30 minutes
CACHE_TTL_FUNDS=1800
CACHE_TTL_CHAT=300                   # 5 minutes

# ── Rate Limiting ─────────────────────────────────────────
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=3600               # 1 hour

# ── CrewAI ────────────────────────────────────────────────
CREW_TIMEOUT_SECONDS=90
ENABLE_CREW_MEMORY=true
ENABLE_CREW_CACHE=true

# ── Optional External APIs ────────────────────────────────
NEWSAPI_KEY=...                      # newsapi.org — 100 req/day free
SERPER_API_KEY=...                   # serper.dev — 2500 searches/month free

# ── App ───────────────────────────────────────────────────
ENVIRONMENT=development              # development | staging | production
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]
```

---

## Testing

Tests are split into **unit tests** (no server or Redis required) and **integration tests** (require a running server and Redis).

```bash
cd backend

# Unit tests only — always runnable
python -m pytest tests/test_job_store.py tests/test_output_models.py \
  tests/test_crew_service.py tests/test_chat_service.py \
  tests/test_recommendations_service.py tests/test_intent_classifier.py -v

# All unit tests (excluding integration)
python -m pytest tests/ -v \
  --ignore=tests/test_chat.py \
  --ignore=tests/test_stocks.py \
  --ignore=tests/test_funds.py

# Integration tests (requires uvicorn + Redis running)
python -m pytest tests/test_chat.py tests/test_stocks.py tests/test_funds.py tests/test_health.py -v

# All tests
python -m pytest tests/ -v
```

**Note:** `asyncio_mode = "auto"` is set in `pyproject.toml` — do not add `@pytest.mark.asyncio` decorators.

---

## Development Guide

### Code Quality

```bash
cd backend

# Format
ruff format .

# Lint
ruff check .

# Type check
mypy app/
```

### Adding a New Feature

| What | Where |
|---|---|
| New API endpoint | `app/api/v1/<name>.py`, register in `app/api/v1/router.py` |
| New AI agent | `app/crew/agents.py` |
| New tool | `app/crew/tools/<name>.py` |
| New request/response model | `app/models/requests.py` / `app/models/responses.py` |
| New service | `app/services/<name>.py`, wire via `app/dependencies.py` |

### Key Patterns

**Structured crew output** — Tasks use `output_pydantic=<Model>` so agents return validated Pydantic objects. Always access results via `result.pydantic`, never `str(result)`.

**Intent-driven chat** — `classify_intent(message)` uses Groq (llama-3.3-70b-versatile) in JSON mode to return `{"needs_news": bool, "needs_metrics": bool}`, then selects tasks accordingly.

**Async job pattern** — `POST` returns `job_id` immediately; background crew runs and writes to Redis job store; `GET /{job_id}` polls until `completed` or `failed`.

### Documentation Conventions

| Type | Location |
|---|---|
| Code reviews | `docs/reviews/<desc>_review.md` |
| Implementation plans | `docs/plan/<desc>_plan.md` |
| Design specs | `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` |

---

## Roadmap

### In Progress

- **Frontend Interface** — A React-based web application is currently under development. It will provide a conversational chat interface for stock Q&A, a dashboard for viewing sector recommendations, and a fund browser with filtering. The frontend will consume the existing REST API and is planned to ship as the `frontend/` directory in this repository.

### Planned Backend Improvements

- Parallel hierarchical recommendations — run sector analysis and stock analysis in parallel using CrewAI `HierarchicalProcess` for significantly faster results
- WebSocket support for streaming crew agent updates in real time
- Portfolio analysis endpoint — analyze a user-submitted portfolio against current market conditions
- Persistent job history — optional PostgreSQL backing for job store to survive Redis restarts

---

## Troubleshooting

**Redis connection error**
```
ConnectionError: Error 111 connecting to localhost:6379
```
Ensure Redis is running: `docker ps | grep redis`. Start it with `docker run -d -p 6379:6379 redis:7-alpine`.

**LLM API errors / quota exceeded**
```
RateLimitError or AuthenticationError
```
Verify your `GROQ_API_KEY` in `.env`. Test: `curl https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY"`

**Crew timeout**
```
TimeoutError during stock analysis
```
Increase `CREW_TIMEOUT_SECONDS` in `.env` (default: 90). Analysis with news + metrics can take 60–120 seconds.

**Rate limit exceeded**
```
429 Too Many Requests
```
Increase `RATE_LIMIT_REQUESTS` in `.env` for local development.

**Indian stock symbols not resolving**
Use base symbols without the `.NS` suffix (e.g., `RELIANCE`, `TCS`, `INFY`). The validator appends `.NS` automatically.

---

## Acknowledgments

- [CrewAI](https://crewai.com/) — Multi-agent orchestration framework
- [FastAPI](https://fastapi.tiangolo.com/) — Modern async Python web framework
- [yfinance](https://github.com/ranaroussi/yfinance) — Yahoo Finance market data
- [Groq](https://groq.com/) — Fast LLM inference (free tier)
- [Redis](https://redis.io/) — Caching and job queue storage

---

## License

MIT License. See [LICENSE](LICENSE) for details.
