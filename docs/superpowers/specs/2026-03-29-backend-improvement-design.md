# Backend Improvement Design
**Date:** 2026-03-29
**Scope:** `stocks_analyzer_be_01` — targeted refactor + fixes (Option B)
**API contracts:** No breaking changes to existing endpoints

---

## 1. Bug Fixes & Quick Wins

Self-contained fixes with no structural impact:

| # | Location | Issue | Fix |
|---|----------|-------|-----|
| 1 | `app/services/job_store.py:57` | Mutable default argument `result: dict = {}` | Change to `result: Optional[dict] = None` |
| 2 | `app/main.py:252` | `redis_client.ping()` called synchronously in async context | Change to `await redis_client.ping()` |
| 3 | `app/services/intent_classifier.py:37` | `AsyncGroq` client instantiated on every call | Module-level `_groq_client: Optional[AsyncGroq] = None`, initialized on first call and reused |
| 4 | `app/api/v1/chat.py:61` | `else: stock_symbol = "AAPL"` silent fallback | Raise `ValidationError` — symbol is required |
| 5 | `app/crew/tools/financial_data.py:3` | `from openai import BaseModel` stale import | Remove |
| 6 | `app/api/v1/stocks.py` + `funds.py` | `market_value = params.market or "ALL"` assigned twice | Remove duplicate assignment |

---

## 2. Structured Output Parsing

### Problem
`_parse_top_sectors` returns hardcoded sector data regardless of crew output. `_parse_stock_recommendations` returns a fake `"STOCK1"` placeholder. `_parse_chat_result` discards sources and reasoning. The crew's real AI-generated output is never used.

### Solution: `app/crew/output_models.py` (new file)

Pydantic models used as `output_pydantic` on CrewAI tasks, forcing agents to return validated structured data:

```
SectorRankingOutput
  └─ sectors: List[SectorInfo]
       └─ name: str, performance_pct: float, trend: str, momentum: str, drivers: str

StockPickOutput
  └─ symbol: str, company_name: str, current_price: float, currency: str
  └─ change_percent: float, recommendation_score: float, reasoning: str
  └─ key_metrics: KeyMetricsOutput (pe_ratio, market_cap, volume, eps, debt_to_equity, roe)

SectorStocksOutput
  └─ sector: str, market: str
  └─ stocks: List[StockPickOutput]

ChatAnswerOutput
  └─ response: str, sources: List[Source], agent_reasoning: str
  └─ (Source reuses existing model from app/models/requests.py: title, url, date)

FundPickOutput
  └─ symbol: str, name: str, current_nav: float, currency: str
  └─ expense_ratio: Optional[float], aum: Optional[str]
  └─ change_percent: float, recommendation_score: float, reasoning: str

SectorFundsOutput
  └─ sector: str, market: str
  └─ funds: List[FundPickOutput]
```

### Task changes in `app/crew/tasks.py`

Each existing task gets `output_pydantic=<Model>`. The description/expected_output prose is preserved (guides agent behavior) but the Pydantic contract enforces structure.

### Parser replacement in new service files

The three `_parse_*` stub methods are deleted from `crew_service.py`. In the new service files, crew outputs are accessed directly via `result.pydantic`:
- `result.pydantic.sectors` (in `recommendations_service.py`) replaces `_parse_top_sectors`
- `result.pydantic.stocks` (in `recommendations_service.py`) replaces `_parse_stock_recommendations`
- `result.pydantic` (in `chat_service.py`) replaces `_parse_chat_result`

---

## 3. Service Layer Split

### Problem
`crew_service.py` is a 539-line god object. Fund recommendations delegate entirely to stock recommendations with no fund-specific logic.

### New structure

**`app/services/chat_service.py`** (new)
- Owns `execute_chat_query(message, stock_symbol, market, job_id)`
- Manages: market researcher + data analyst + advisor agents
- Intent-driven task selection (news / metrics / both)
- Parses `ChatAnswerOutput` from crew result

**`app/services/recommendations_service.py`** (new)
- Owns `execute_stock_recommendations(market, timeframe, job_id)`
  - Sector identification crew → `SectorRankingOutput`
  - Per-sector stock picking crew → `SectorStocksOutput` (3 sectors × 3 stocks = 9 total)
  - Multi-market `ALL` support: runs US then IN, combines results
- Owns `execute_fund_recommendations(market, timeframe, job_id)` — **fully separate from stocks**
  - Uses `identify_top_etfs_in_sector` task (new, see below)
  - Targets ETF symbols (XLK, XLF, etc. for US; Nifty sectoral ETFs for India)
  - Fetches NAV, expense ratio, AUM via yfinance
  - Parses `SectorFundsOutput`

**`app/services/crew_service.py`** (kept as thin facade)
- Re-exports `ChatService` and `RecommendationsService` so `dependencies.py` and existing imports are unaffected
- Can be removed in a future cleanup once all consumers are updated

### New tasks in `app/crew/tasks.py`

**`identify_top_etfs_in_sector(agent, sector, market, timeframe)`**
- Description targets ETF symbols explicitly (XLK for US Tech, `^CNXIT` for India IT, etc.)
- Uses `YFinanceDataTool` to fetch NAV history, `SectorPerformanceTool` for sector context
- `output_pydantic=SectorFundsOutput`

**`synthesize_fund_response(agent, sector, market)`**
- Synthesizes ETF picks from the data analyst's output
- `output_pydantic=SectorFundsOutput`

---

## 4. Tests

### Updated tests (fix assertions for new structured outputs)

| File | Change |
|------|--------|
| `tests/test_chat.py` | Assert `response` is non-empty string, `sources` is a list, `agent_reasoning` is not None |
| `tests/test_stocks.py` | Assert recommendations contain real symbol strings (not `"STOCK1"`), real sector names |
| `tests/test_funds.py` | Assert `current_nav`, `expense_ratio`, `aum` are populated; assert fund response differs from stock response |

### New tests

**`tests/test_output_models.py`** (unit, no server)
- Valid construction of each output model
- Field validation (e.g. `recommendation_score` out of 0-10 range)
- Serialization round-trip (model → dict → model)

**`tests/test_chat_service.py`** (unit, mocked crew + Redis)
- Correct agent subset selected per intent (news-only → no data_analyst task)
- Timeout raises `CrewExecutionError`
- `job_store.update_job` called with correct status progression

**`tests/test_recommendations_service.py`** (unit, mocked crew + Redis)
- Sector crew fires before stock crew
- Fund crew uses ETF symbols, not stock symbols
- `ALL` market combines US + IN results
- Failed sector crew propagates error to job_store

**`tests/test_job_store.py`** (unit, mocked Redis)
- `update_job` with `result=None` does not overwrite existing result
- Job TTL is set on creation
- `get_job` returns None for missing job_id

---

## File Change Summary

| File | Action |
|------|--------|
| `app/crew/output_models.py` | **New** — Pydantic output models |
| `app/services/chat_service.py` | **New** — extracted from crew_service |
| `app/services/recommendations_service.py` | **New** — extracted + fund logic |
| `app/services/crew_service.py` | **Modified** — thin facade only |
| `app/crew/tasks.py` | **Modified** — add `output_pydantic`, add 2 fund tasks |
| `app/crew/tools/financial_data.py` | **Modified** — remove stale import |
| `app/services/intent_classifier.py` | **Modified** — Groq singleton |
| `app/services/job_store.py` | **Modified** — mutable default fix |
| `app/main.py` | **Modified** — await ping fix |
| `app/api/v1/chat.py` | **Modified** — remove AAPL fallback |
| `app/api/v1/stocks.py` | **Modified** — remove duplicate market_value |
| `app/api/v1/funds.py` | **Modified** — remove duplicate market_value |
| `tests/test_output_models.py` | **New** |
| `tests/test_chat_service.py` | **New** |
| `tests/test_recommendations_service.py` | **New** |
| `tests/test_job_store.py` | **New** |
| `tests/test_chat.py` | **Modified** |
| `tests/test_stocks.py` | **Modified** |
| `tests/test_funds.py` | **Modified** |

---

## Out of Scope

- Frontend (planned as next phase)
- CrewAI YAML-driven agent config migration
- FinBERT-based sentiment analysis (currently keyword-based, noted as TODO in code)
- India mutual fund support (noted as "coming soon" in code)
- Dynamic sector stock discovery (currently static hardcoded lists)
