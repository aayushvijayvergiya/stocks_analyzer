# Backend Improvement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all bugs, stubs, and structural issues in `stocks_analyzer_be_01` so the backend returns real AI-generated data with no placeholder responses.

**Architecture:** Bug fixes first (no test changes required), then Pydantic output models as the foundation for real data flow, then service split (ChatService + RecommendationsService), with the existing CrewService becoming a thin backward-compatible facade.

**Tech Stack:** Python 3.12, FastAPI, CrewAI, Pydantic v2, Redis (aioredis), yfinance, Groq LLM, pytest + pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-03-29-backend-improvement-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `app/crew/tools/financial_data.py` | Modify | Remove stale `from openai import BaseModel` |
| `app/services/job_store.py` | Modify | Fix mutable default `result: dict = {}` → `Optional[dict] = None` |
| `app/main.py` | Modify | Fix `redis_client.ping()` → `await redis_client.ping()` |
| `app/services/intent_classifier.py` | Modify | Module-level Groq singleton |
| `app/api/v1/chat.py` | Modify | Remove AAPL silent fallback |
| `app/api/v1/stocks.py` | Modify | Remove duplicate `market_value` assignment |
| `app/api/v1/funds.py` | Modify | Remove duplicate `market_value` assignment |
| `app/crew/output_models.py` | **New** | Pydantic models for crew structured output |
| `app/crew/tasks.py` | Modify | Add `output_pydantic` to 3 tasks; add `identify_top_etfs_in_sector` task |
| `app/services/chat_service.py` | **New** | Chat crew execution with structured output parsing |
| `app/services/recommendations_service.py` | **New** | Stock + fund crew execution, separate ETF logic |
| `app/services/crew_service.py` | Modify | Thin facade delegating to ChatService + RecommendationsService |
| `app/services/__init__.py` | Modify | Export ChatService, RecommendationsService |
| `tests/test_job_store.py` | **New** | Unit tests for JobStore fixes |
| `tests/test_output_models.py` | **New** | Unit tests for output_models.py |
| `tests/test_chat_service.py` | **New** | Unit tests for ChatService |
| `tests/test_recommendations_service.py` | **New** | Unit tests for RecommendationsService |
| `tests/test_chat.py` | Modify | Update assertions for real structured output |
| `tests/test_stocks.py` | Modify | Update assertions for real structured output |
| `tests/test_funds.py` | Modify | Update assertions for real fund data |

---

## Task 1: Fix stale import and mutable default bug

**Files:**
- Modify: `app/crew/tools/financial_data.py:1-3`
- Modify: `app/services/job_store.py:51-57`
- Create: `tests/test_job_store.py`

- [ ] **Step 1: Write the failing test for mutable default bug**

Create `tests/test_job_store.py`:

```python
"""Unit tests for JobStore."""
import json
import pytest
from unittest.mock import AsyncMock
from app.services.job_store import JobStore


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    return redis


@pytest.fixture
def job_store(mock_redis):
    return JobStore(redis_client=mock_redis)


@pytest.mark.asyncio
async def test_create_job_sets_ttl(job_store, mock_redis):
    await job_store.create_job("job-1", "chat")
    mock_redis.set.assert_called_once()
    call_kwargs = mock_redis.set.call_args.kwargs
    assert call_kwargs.get("ex") == 3600


@pytest.mark.asyncio
async def test_get_job_returns_none_for_missing_job(job_store, mock_redis):
    mock_redis.get.return_value = None
    result = await job_store.get_job("nonexistent-job")
    assert result is None


@pytest.mark.asyncio
async def test_update_job_none_result_does_not_overwrite_existing(job_store, mock_redis):
    """After fix: passing result=None (default) must not overwrite an existing result."""
    existing = {
        "job_id": "job-1", "type": "chat", "status": "processing",
        "progress": "Working...", "created_at": "2026-03-29T00:00:00+00:00",
        "completed_at": None, "result": {"response": "original"}, "error": None
    }
    mock_redis.get.return_value = json.dumps(existing)

    await job_store.update_job("job-1", "completed")

    saved = json.loads(mock_redis.set.call_args[0][1])
    assert saved["result"] == {"response": "original"}


@pytest.mark.asyncio
async def test_update_job_sets_completed_at_on_completion(job_store, mock_redis):
    existing = {
        "job_id": "job-1", "type": "chat", "status": "processing",
        "progress": "Working...", "created_at": "2026-03-29T00:00:00+00:00",
        "completed_at": None, "result": None, "error": None
    }
    mock_redis.get.return_value = json.dumps(existing)

    await job_store.update_job("job-1", "completed")

    saved = json.loads(mock_redis.set.call_args[0][1])
    assert saved["completed_at"] is not None
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd stocks_analyzer_be_01
pytest tests/test_job_store.py -v
```

Expected: `FAILED tests/test_job_store.py::test_update_job_none_result_does_not_overwrite_existing` (current code passes `{}` which is not None, so it overwrites)

- [ ] **Step 3: Fix mutable default in job_store.py**

In `app/services/job_store.py`, replace the function signature at line 51:

```python
# BEFORE
async def update_job(
    self,
    job_id: str,
    status: str,
    progress: str = '',
    result: dict = {},
    error: str = ''
) -> bool:
```

```python
# AFTER
async def update_job(
    self,
    job_id: str,
    status: str,
    progress: str = '',
    result: Optional[dict] = None,
    error: Optional[str] = None
) -> bool:
```

`Optional` is already imported at the top of the file. Also update the conditional checks further down — replace:

```python
        if progress is not None:
            job_data["progress"] = progress

        if result is not None:
            job_data["result"] = result

        if error is not None:
            job_data["error"] = error
```

with (unchanged logic — `None` default now correctly skips overwrites):

```python
        if progress:
            job_data["progress"] = progress

        if result is not None:
            job_data["result"] = result

        if error is not None:
            job_data["error"] = error
```

- [ ] **Step 4: Remove stale import in financial_data.py**

In `app/crew/tools/financial_data.py`, remove line 3:

```python
# DELETE this line entirely:
from openai import BaseModel
```

The file already has `from pydantic import BaseModel, Field` on line 8 which is the correct import.

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_job_store.py -v
```

Expected: all 4 tests PASS

- [ ] **Step 6: Commit**

```bash
cd stocks_analyzer_be_01
git add app/services/job_store.py app/crew/tools/financial_data.py tests/test_job_store.py
git commit -m "fix: mutable default in update_job, remove stale openai import"
```

---

## Task 2: Fix async ping in health check

**Files:**
- Modify: `app/main.py:250-254`

- [ ] **Step 1: Fix the sync ping call**

In `app/main.py`, find the health check function and replace:

```python
# BEFORE
    redis_status = "disconnected"
    try:
        redis_client = await get_redis()
        if redis_client:
            redis_client.ping()
            redis_status = "connected"
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
```

```python
# AFTER
    redis_status = "disconnected"
    try:
        redis_client = await get_redis()
        if redis_client:
            await redis_client.ping()
            redis_status = "connected"
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
```

- [ ] **Step 2: Verify existing health test still passes**

```bash
pytest tests/test_health.py -v
```

Expected: all tests PASS (the test_health.py tests require a running server; if server isn't running, skip with `pytest tests/test_health.py -v -k "not test_health"` — the fix is trivially correct)

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "fix: await redis ping in health check endpoint"
```

---

## Task 3: Fix intent classifier Groq singleton

**Files:**
- Modify: `app/services/intent_classifier.py`

- [ ] **Step 1: Replace per-call client instantiation with singleton**

Replace the entire contents of `app/services/intent_classifier.py` with:

```python
"""
Intent Classifier for Financial Queries.

Uses Groq for fast, free intent classification with JSON outputs.
"""

import json
from typing import Dict, Optional
from groq import AsyncGroq

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

_groq_client: Optional[AsyncGroq] = None


def _get_groq_client() -> AsyncGroq:
    """Return module-level Groq client, creating it on first call."""
    global _groq_client
    if _groq_client is None:
        _groq_client = AsyncGroq(
            api_key=settings.GROQ_API_KEY.get_secret_value() if settings.GROQ_API_KEY else None
        )
    return _groq_client


async def classify_intent(message: str) -> Dict[str, bool]:
    """Classify user intent using Groq LLM.

    Args:
        message: User's financial query

    Returns:
        Dict with intent flags: {
            "needs_news": bool,
            "needs_metrics": bool,
            "needs_analysis": bool,
            "needs_comparison": bool
        }

    Example:
        >>> intent = await classify_intent("What's the latest AAPL news?")
        >>> print(intent)
        {"needs_news": True, "needs_metrics": False, ...}
    """
    try:
        client = _get_groq_client()

        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": """You are an intent classifier for financial queries. Return JSON with these keys:
{"needs_news": true/false, "needs_metrics": true/false, "needs_analysis": true/false, "needs_comparison": true/false}

Guidelines:
- needs_news: User wants recent events, news, announcements, or developments
- needs_metrics: User wants financial data like price, ratios, earnings, revenue
- needs_analysis: User wants investment advice, recommendations, or forecasts
- needs_comparison: User is comparing multiple stocks

Multiple can be true. If unclear, default needs_metrics=true."""
                },
                {
                    "role": "user",
                    "content": message
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=100
        )

        content = response.choices[0].message.content
        if content is None:
            raise ValueError("Empty response from Groq")
        intent = json.loads(content)
        logger.info(f"Classified intent for '{message[:50]}': {intent}")

        return {
            "needs_news": intent.get("needs_news", False),
            "needs_metrics": intent.get("needs_metrics", False),
            "needs_analysis": intent.get("needs_analysis", False),
            "needs_comparison": intent.get("needs_comparison", False),
        }

    except Exception as e:
        logger.warning(f"Groq classification failed: {e}, defaulting to metrics")
        return {
            "needs_news": False,
            "needs_metrics": True,
            "needs_analysis": False,
            "needs_comparison": False,
        }
```

- [ ] **Step 2: Run existing intent classifier tests**

```bash
pytest tests/test_intent_classifier.py -v
```

Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add app/services/intent_classifier.py
git commit -m "fix: groq client singleton in intent_classifier to avoid per-call instantiation"
```

---

## Task 4: Fix chat AAPL fallback + duplicate market_value

**Files:**
- Modify: `app/api/v1/chat.py:53-71`
- Modify: `app/api/v1/stocks.py:112-132`
- Modify: `app/api/v1/funds.py:115-135`

- [ ] **Step 1: Fix chat.py AAPL fallback**

In `app/api/v1/chat.py`, replace the try block opening logic:

```python
# BEFORE
        stock_symbol = request.stock_symbol
        market = request.market

        if stock_symbol:
            stock_symbol, market = validate_and_normalize_symbol(
                stock_symbol,
                market
            )
        else:
            # Try to extract symbol from message
            # TODO: Implement symbol extraction from natural language
            stock_symbol = "AAPL"  # Default for now
            market = "US"
```

```python
# AFTER
        stock_symbol = request.stock_symbol
        market = request.market

        if not stock_symbol:
            raise HTTPException(
                status_code=400,
                detail="stock_symbol is required. Provide a symbol like 'AAPL' or 'RELIANCE.NS'."
            )

        stock_symbol, market = validate_and_normalize_symbol(stock_symbol, market)
```

- [ ] **Step 2: Fix duplicate market_value in stocks.py**

In `app/api/v1/stocks.py`, find the `create_stock_recommendations` function and remove the duplicate assignment. The block currently reads:

```python
        # Check cache first
        market_value = params.market or "ALL"
        cache_key = make_stock_cache_key(params.timeframe, market_value)
        ...
        # Start background analysis
        market_value = params.market or "ALL"   # <-- DUPLICATE, remove this line
        background_tasks.add_task(
```

Delete the second `market_value = params.market or "ALL"` line so it reads:

```python
        # Check cache first
        market_value = params.market or "ALL"
        cache_key = make_stock_cache_key(params.timeframe, market_value)
        ...
        # Start background analysis
        background_tasks.add_task(
```

- [ ] **Step 3: Fix duplicate market_value in funds.py**

Same fix in `app/api/v1/funds.py` — remove the second `market_value = params.market or "ALL"` assignment in `create_fund_recommendations`.

- [ ] **Step 4: Run existing chat tests**

```bash
pytest tests/test_chat.py -v
```

Expected: tests that previously passed still pass; any test that sends a request without `stock_symbol` should now get a 400 (update that test if needed).

- [ ] **Step 5: Commit**

```bash
git add app/api/v1/chat.py app/api/v1/stocks.py app/api/v1/funds.py
git commit -m "fix: require stock_symbol in chat, remove duplicate market_value assignments"
```

---

## Task 5: Create output_models.py with tests

**Files:**
- Create: `app/crew/output_models.py`
- Create: `tests/test_output_models.py`

- [ ] **Step 1: Write the failing tests first**

Create `tests/test_output_models.py`:

```python
"""Unit tests for crew structured output models."""
import pytest
from pydantic import ValidationError
from app.crew.output_models import (
    SectorInfo,
    SectorRankingOutput,
    KeyMetricsOutput,
    StockPickOutput,
    SectorStocksOutput,
    ChatAnswerOutput,
    FundPickOutput,
    SectorFundsOutput,
)
from app.models.requests import Source


# ── SectorRankingOutput ──────────────────────────────────────────────────────

def test_sector_ranking_output_valid_construction():
    output = SectorRankingOutput(sectors=[
        SectorInfo(
            name="Technology", performance_pct=12.5,
            trend="Strong Uptrend", momentum="Accelerating", drivers="AI boom"
        )
    ])
    assert len(output.sectors) == 1
    assert output.sectors[0].name == "Technology"
    assert output.sectors[0].performance_pct == 12.5


def test_sector_ranking_output_empty_sectors():
    output = SectorRankingOutput(sectors=[])
    assert output.sectors == []


# ── StockPickOutput ──────────────────────────────────────────────────────────

def test_stock_pick_output_valid():
    stock = StockPickOutput(
        symbol="AAPL", company_name="Apple Inc.",
        current_price=175.0, currency="USD",
        change_percent=2.5, recommendation_score=8.5,
        reasoning="Strong fundamentals and solid earnings growth."
    )
    assert stock.symbol == "AAPL"
    assert stock.key_metrics is None


def test_stock_pick_output_score_too_high_raises():
    with pytest.raises(ValidationError):
        StockPickOutput(
            symbol="AAPL", company_name="Apple Inc.",
            current_price=175.0, currency="USD",
            change_percent=2.5, recommendation_score=11.0,
            reasoning="Great stock."
        )


def test_stock_pick_output_score_too_low_raises():
    with pytest.raises(ValidationError):
        StockPickOutput(
            symbol="AAPL", company_name="Apple Inc.",
            current_price=175.0, currency="USD",
            change_percent=2.5, recommendation_score=-1.0,
            reasoning="Bad stock."
        )


def test_stock_pick_output_with_key_metrics():
    stock = StockPickOutput(
        symbol="AAPL", company_name="Apple Inc.",
        current_price=175.0, currency="USD",
        change_percent=2.5, recommendation_score=8.5,
        reasoning="Solid.",
        key_metrics=KeyMetricsOutput(pe_ratio=28.5, roe=0.35)
    )
    assert stock.key_metrics.pe_ratio == 28.5
    assert stock.key_metrics.market_cap is None


# ── SectorStocksOutput ───────────────────────────────────────────────────────

def test_sector_stocks_output_serialization_roundtrip():
    original = SectorStocksOutput(
        sector="Technology", market="US",
        stocks=[StockPickOutput(
            symbol="AAPL", company_name="Apple Inc.",
            current_price=175.0, currency="USD",
            change_percent=2.5, recommendation_score=8.5,
            reasoning="Strong fundamentals."
        )]
    )
    as_dict = original.model_dump()
    restored = SectorStocksOutput(**as_dict)
    assert restored.stocks[0].symbol == "AAPL"
    assert restored.sector == "Technology"


# ── ChatAnswerOutput ─────────────────────────────────────────────────────────

def test_chat_answer_output_valid():
    output = ChatAnswerOutput(
        response="Apple is trading at $175",
        sources=[Source(title="Reuters", url="https://reuters.com", date="2026-03-29")],
        agent_reasoning="Based on current price data from yfinance."
    )
    assert output.response == "Apple is trading at $175"
    assert len(output.sources) == 1
    assert output.sources[0].title == "Reuters"


def test_chat_answer_output_empty_sources():
    output = ChatAnswerOutput(
        response="AAPL current price is $175.",
        sources=[],
        agent_reasoning="Fetched from yfinance."
    )
    assert output.sources == []


# ── FundPickOutput ───────────────────────────────────────────────────────────

def test_fund_pick_output_optional_fields_default_none():
    fund = FundPickOutput(
        symbol="XLK", name="Technology Select Sector SPDR",
        current_nav=195.0, currency="USD",
        change_percent=3.2, recommendation_score=8.0,
        reasoning="Top tech ETF by AUM and liquidity."
    )
    assert fund.expense_ratio is None
    assert fund.aum is None


def test_fund_pick_output_with_all_fields():
    fund = FundPickOutput(
        symbol="XLK", name="Technology Select Sector SPDR",
        current_nav=195.0, currency="USD",
        expense_ratio=0.13, aum="$50B",
        change_percent=3.2, recommendation_score=8.0,
        reasoning="Top tech ETF."
    )
    assert fund.expense_ratio == 0.13
    assert fund.aum == "$50B"


def test_fund_pick_output_score_bounds():
    with pytest.raises(ValidationError):
        FundPickOutput(
            symbol="XLK", name="Tech SPDR",
            current_nav=195.0, currency="USD",
            change_percent=3.2, recommendation_score=10.5,
            reasoning="Great."
        )


# ── SectorFundsOutput ────────────────────────────────────────────────────────

def test_sector_funds_output_serialization_roundtrip():
    original = SectorFundsOutput(
        sector="Technology", market="US",
        funds=[FundPickOutput(
            symbol="XLK", name="Technology Select Sector SPDR",
            current_nav=195.0, currency="USD",
            change_percent=3.2, recommendation_score=8.0,
            reasoning="Top tech ETF."
        )]
    )
    as_dict = original.model_dump()
    restored = SectorFundsOutput(**as_dict)
    assert restored.funds[0].symbol == "XLK"
    assert restored.market == "US"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_output_models.py -v
```

Expected: `ImportError: cannot import name 'SectorInfo' from 'app.crew.output_models'` (file doesn't exist yet)

- [ ] **Step 3: Create app/crew/output_models.py**

```python
"""
Pydantic output models for CrewAI structured task outputs.

These are used as `output_pydantic` on Task definitions so agents return
validated, typed data instead of free-form text.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from app.models.requests import Source


class SectorInfo(BaseModel):
    """A single sector with performance data."""
    name: str
    performance_pct: float
    trend: str
    momentum: str
    drivers: str


class SectorRankingOutput(BaseModel):
    """Output of identify_top_sectors task."""
    sectors: List[SectorInfo]


class KeyMetricsOutput(BaseModel):
    """Financial metrics for a single stock."""
    pe_ratio: Optional[float] = None
    market_cap: Optional[float] = None
    volume: Optional[int] = None
    eps: Optional[float] = None
    debt_to_equity: Optional[float] = None
    roe: Optional[float] = None


class StockPickOutput(BaseModel):
    """A single stock recommendation."""
    symbol: str
    company_name: str
    current_price: float
    currency: str
    change_percent: float
    recommendation_score: float = Field(ge=0, le=10)
    reasoning: str
    key_metrics: Optional[KeyMetricsOutput] = None


class SectorStocksOutput(BaseModel):
    """Output of find_top_stocks_in_sector task."""
    sector: str
    market: str
    stocks: List[StockPickOutput]


class ChatAnswerOutput(BaseModel):
    """Output of synthesize_chat_response task."""
    response: str
    sources: List[Source]
    agent_reasoning: str


class FundPickOutput(BaseModel):
    """A single ETF/fund recommendation."""
    symbol: str
    name: str
    current_nav: float
    currency: str
    expense_ratio: Optional[float] = None
    aum: Optional[str] = None
    change_percent: float
    recommendation_score: float = Field(ge=0, le=10)
    reasoning: str


class SectorFundsOutput(BaseModel):
    """Output of identify_top_etfs_in_sector task."""
    sector: str
    market: str
    funds: List[FundPickOutput]
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_output_models.py -v
```

Expected: all 16 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/crew/output_models.py tests/test_output_models.py
git commit -m "feat: add pydantic output models for crew structured outputs"
```

---

## Task 6: Update tasks.py with output_pydantic and new ETF task

**Files:**
- Modify: `app/crew/tasks.py`

- [ ] **Step 1: Add import for output models at top of tasks.py**

In `app/crew/tasks.py`, add to the imports section (after existing imports):

```python
from app.crew.output_models import (
    SectorRankingOutput,
    SectorStocksOutput,
    ChatAnswerOutput,
    SectorFundsOutput,
)
```

- [ ] **Step 2: Add output_pydantic to identify_top_sectors**

In `app/crew/tasks.py`, find `identify_top_sectors` and add `output_pydantic=SectorRankingOutput` to the Task constructor:

```python
    @staticmethod
    def identify_top_sectors(agent, market: str, timeframe: str) -> Task:
        """Task: Identify and rank top performing sectors."""
        return Task(
            description=f"""Identify the top 3 performing sectors in the {market} market over the {timeframe} timeframe.

            Your objectives:
            1. Analyze performance of all major sectors
            2. Rank sectors by performance (% gain/loss)
            3. Identify momentum and trends in each sector
            4. Understand what's driving sector performance
            5. Select the top 3 performing sectors

            Market: {market}
            Timeframe: {timeframe}
            Date: {datetime.now().strftime('%Y-%m-%d')}

            Use sector performance tools to analyze ETFs (US) or indices (India).
            """,
            expected_output=f"""Return a JSON object matching this exact schema:
            {{
              "sectors": [
                {{
                  "name": "Technology",
                  "performance_pct": 12.5,
                  "trend": "Strong Uptrend",
                  "momentum": "Accelerating",
                  "drivers": "Brief explanation of what is driving this sector"
                }}
              ]
            }}
            Include exactly 3 sectors ranked by performance_pct descending.""",
            agent=agent,
            output_pydantic=SectorRankingOutput,
        )
```

- [ ] **Step 3: Add output_pydantic to find_top_stocks_in_sector**

```python
    @staticmethod
    def find_top_stocks_in_sector(agent, sector: str, market: str, timeframe: str) -> Task:
        """Task: Find and rank top stocks within a sector."""
        return Task(
            description=f"""Find the top 3 stock picks in the {sector} sector for the {market} market.

            Your objectives:
            1. Get list of major stocks in the {sector} sector
            2. Fetch financial data and performance for each stock
            3. Analyze and compare stocks based on:
               - Financial health (P/E, ROE, debt levels)
               - Recent performance ({timeframe})
               - Growth prospects
               - Market position
            4. Rank and select the top 3 best opportunities
            5. Provide clear reasoning for each selection

            Sector: {sector}
            Market: {market}
            Timeframe: {timeframe}
            """,
            expected_output=f"""Return a JSON object matching this exact schema:
            {{
              "sector": "{sector}",
              "market": "{market}",
              "stocks": [
                {{
                  "symbol": "AAPL",
                  "company_name": "Apple Inc.",
                  "current_price": 175.50,
                  "currency": "USD",
                  "change_percent": 5.2,
                  "recommendation_score": 8.5,
                  "reasoning": "3-4 sentence explanation",
                  "key_metrics": {{
                    "pe_ratio": 28.5,
                    "market_cap": 2800000000000.0,
                    "volume": 50000000,
                    "eps": 6.13,
                    "debt_to_equity": 1.8,
                    "roe": 0.35
                  }}
                }}
              ]
            }}
            Include exactly 3 stocks. All numeric fields must be numbers, not strings.""",
            agent=agent,
            output_pydantic=SectorStocksOutput,
        )
```

- [ ] **Step 4: Add output_pydantic to synthesize_chat_response**

```python
    @staticmethod
    def synthesize_chat_response(agent, user_question: str, stock_symbol: str, market: str) -> Task:
        """Task: Answer user's question about a stock (for chat endpoint)."""
        return Task(
            description=f"""Answer the user's question about {stock_symbol} in a helpful, accurate, and concise way.

            User Question: "{user_question}"
            Stock Symbol: {stock_symbol}
            Market: {market}

            Your approach:
            1. Understand what the user is asking (price, news, recommendation, comparison, etc.)
            2. Gather relevant information from prior task outputs
            3. Provide a conversational, helpful answer
            4. Cite sources where appropriate
            5. Keep it concise (200-400 words)
            """,
            expected_output=f"""Return a JSON object matching this exact schema:
            {{
              "response": "Your conversational answer here (200-400 words)",
              "sources": [
                {{
                  "title": "Article or data source title",
                  "url": "https://source-url.com",
                  "date": "YYYY-MM-DD"
                }}
              ],
              "agent_reasoning": "Brief explanation of how you arrived at this answer"
            }}
            The response must directly answer the user's question. sources can be an empty list if no external sources were used.""",
            agent=agent,
            output_pydantic=ChatAnswerOutput,
        )
```

- [ ] **Step 5: Add identify_top_etfs_in_sector task**

Add this new static method to the `FinancialTasks` class:

```python
    @staticmethod
    def identify_top_etfs_in_sector(agent, sector: str, market: str, timeframe: str) -> Task:
        """Task: Find and rank top ETFs/funds within a sector."""
        US_SECTOR_ETFS = {
            "Technology": "XLK", "Healthcare": "XLV", "Financials": "XLF",
            "Consumer Discretionary": "XLY", "Industrials": "XLI", "Energy": "XLE",
            "Materials": "XLB", "Consumer Staples": "XLP", "Utilities": "XLU",
            "Real Estate": "XLRE", "Communication Services": "XLC"
        }
        INDIA_SECTOR_ETFS = {
            "Technology": "^CNXIT", "Banking": "^NSEBANK", "Pharma": "^CNXPHARMA",
            "Auto": "^CNXAUTO", "FMCG": "^CNXFMCG", "Metal": "^CNXMETAL",
            "Realty": "^CNXREALTY", "Financial Services": "^CNXFIN"
        }
        etf_map = US_SECTOR_ETFS if market == "US" else INDIA_SECTOR_ETFS
        primary_etf = etf_map.get(sector, "the sector ETF/index")
        currency = "USD" if market == "US" else "INR"

        return Task(
            description=f"""Find the top 3 ETF or fund picks in the {sector} sector for the {market} market.

            The primary ETF/index for this sector is: {primary_etf}

            Your objectives:
            1. Fetch current NAV/price and historical performance of {primary_etf} over {timeframe}
            2. Identify 2 additional ETFs or sector indices in the {sector} space for {market}
            3. For each ETF/fund fetch: current NAV, expense ratio (if available via yfinance info),
               AUM (if available), and % change over {timeframe}
            4. Rank them by performance and overall quality
            5. Provide clear reasoning for each

            Market: {market}
            Sector: {sector}
            Timeframe: {timeframe}
            Currency: {currency}
            Date: {datetime.now().strftime('%Y-%m-%d')}

            Use the Stock Data Fetcher tool with the ETF symbols.
            For India: use Nifty sectoral indices as proxies where direct ETF data is unavailable.
            """,
            expected_output=f"""Return a JSON object matching this exact schema:
            {{
              "sector": "{sector}",
              "market": "{market}",
              "funds": [
                {{
                  "symbol": "{primary_etf}",
                  "name": "Full ETF name",
                  "current_nav": 195.0,
                  "currency": "{currency}",
                  "expense_ratio": 0.13,
                  "aum": "$50B",
                  "change_percent": 3.2,
                  "recommendation_score": 8.5,
                  "reasoning": "2-3 sentence explanation of why this ETF is recommended"
                }}
              ]
            }}
            Include exactly 3 funds. Set expense_ratio and aum to null if not available from yfinance.
            All numeric fields must be numbers, not strings.""",
            agent=agent,
            output_pydantic=SectorFundsOutput,
        )
```

- [ ] **Step 6: Run existing crew service tests**

```bash
pytest tests/test_crew_service.py -v
```

Expected: all 8 tests PASS (task creation tests still pass since we preserved descriptions)

- [ ] **Step 7: Commit**

```bash
git add app/crew/tasks.py
git commit -m "feat: add output_pydantic to tasks and add identify_top_etfs_in_sector task"
```

---

## Task 7: Create ChatService with tests

**Files:**
- Create: `app/services/chat_service.py`
- Create: `tests/test_chat_service.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_chat_service.py`:

```python
"""Unit tests for ChatService."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.chat_service import ChatService
from app.crew.output_models import ChatAnswerOutput
from app.utils.exceptions import CrewExecutionError
from app.models.requests import Source


@pytest.fixture
def mock_job_store():
    store = AsyncMock()
    store.create_job = AsyncMock()
    store.update_job = AsyncMock()
    return store


@pytest.fixture
def service(mock_job_store):
    return ChatService(job_store=mock_job_store)


def make_mock_crew_result(response="AAPL is at $175", sources=None, reasoning="From yfinance"):
    mock_result = MagicMock()
    mock_result.pydantic = ChatAnswerOutput(
        response=response,
        sources=sources or [Source(title="yfinance", url="https://finance.yahoo.com", date="2026-03-29")],
        agent_reasoning=reasoning
    )
    return mock_result


@pytest.mark.asyncio
async def test_news_intent_calls_research_news_task_not_metrics(service):
    """When intent is news-only, research_stock_news is called but analyze_stock_financials is not."""
    with patch("app.services.chat_service.classify_intent",
               return_value={"needs_news": True, "needs_metrics": False, "needs_analysis": False, "needs_comparison": False}), \
         patch("app.services.chat_service.FinancialTasks.research_stock_news", return_value=MagicMock()) as mock_news, \
         patch("app.services.chat_service.FinancialTasks.analyze_stock_financials", return_value=MagicMock()) as mock_metrics, \
         patch("app.services.chat_service.FinancialTasks.synthesize_chat_response", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.market_researcher", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.financial_data_analyst", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.investment_advisor", return_value=MagicMock()), \
         patch("app.services.chat_service.Crew", return_value=MagicMock()), \
         patch.object(service, "_run_crew_with_timeout", return_value=make_mock_crew_result()):

        await service.execute_chat_query(
            message="What's the latest AAPL news?",
            stock_symbol="AAPL",
            market="US"
        )

    mock_news.assert_called_once()
    mock_metrics.assert_not_called()


@pytest.mark.asyncio
async def test_metrics_intent_calls_financials_task_not_news(service):
    """When intent is metrics-only, analyze_stock_financials is called but research_stock_news is not."""
    with patch("app.services.chat_service.classify_intent",
               return_value={"needs_news": False, "needs_metrics": True, "needs_analysis": False, "needs_comparison": False}), \
         patch("app.services.chat_service.FinancialTasks.research_stock_news", return_value=MagicMock()) as mock_news, \
         patch("app.services.chat_service.FinancialTasks.analyze_stock_financials", return_value=MagicMock()) as mock_metrics, \
         patch("app.services.chat_service.FinancialTasks.synthesize_chat_response", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.market_researcher", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.financial_data_analyst", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.investment_advisor", return_value=MagicMock()), \
         patch("app.services.chat_service.Crew", return_value=MagicMock()), \
         patch.object(service, "_run_crew_with_timeout", return_value=make_mock_crew_result()):

        await service.execute_chat_query(
            message="What is AAPL P/E ratio?",
            stock_symbol="AAPL",
            market="US"
        )

    mock_news.assert_not_called()
    mock_metrics.assert_called_once()


@pytest.mark.asyncio
async def test_no_intent_defaults_to_financials_task(service):
    """When no intent flags are set, analyze_stock_financials is called as default."""
    with patch("app.services.chat_service.classify_intent",
               return_value={"needs_news": False, "needs_metrics": False, "needs_analysis": False, "needs_comparison": False}), \
         patch("app.services.chat_service.FinancialTasks.research_stock_news", return_value=MagicMock()) as mock_news, \
         patch("app.services.chat_service.FinancialTasks.analyze_stock_financials", return_value=MagicMock()) as mock_metrics, \
         patch("app.services.chat_service.FinancialTasks.synthesize_chat_response", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.market_researcher", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.financial_data_analyst", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.investment_advisor", return_value=MagicMock()), \
         patch("app.services.chat_service.Crew", return_value=MagicMock()), \
         patch.object(service, "_run_crew_with_timeout", return_value=make_mock_crew_result()):

        await service.execute_chat_query(
            message="Tell me about AAPL",
            stock_symbol="AAPL",
            market="US"
        )

    mock_metrics.assert_called_once()
    mock_news.assert_not_called()


@pytest.mark.asyncio
async def test_timeout_raises_crew_execution_error(service):
    with patch("app.services.chat_service.classify_intent",
               return_value={"needs_news": False, "needs_metrics": True, "needs_analysis": False, "needs_comparison": False}), \
         patch("app.services.chat_service.FinancialTasks.analyze_stock_financials", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialTasks.synthesize_chat_response", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.market_researcher", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.financial_data_analyst", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.investment_advisor", return_value=MagicMock()), \
         patch("app.services.chat_service.Crew", return_value=MagicMock()), \
         patch.object(service, "_run_crew_with_timeout", side_effect=asyncio.TimeoutError()):

        with pytest.raises(CrewExecutionError, match="timed out"):
            await service.execute_chat_query(
                message="AAPL price?", stock_symbol="AAPL", market="US"
            )


@pytest.mark.asyncio
async def test_job_store_status_progression(service, mock_job_store):
    """Job store must be called: create → processing → completed."""
    with patch("app.services.chat_service.classify_intent",
               return_value={"needs_news": False, "needs_metrics": True, "needs_analysis": False, "needs_comparison": False}), \
         patch("app.services.chat_service.FinancialTasks.analyze_stock_financials", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialTasks.synthesize_chat_response", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.market_researcher", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.financial_data_analyst", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.investment_advisor", return_value=MagicMock()), \
         patch("app.services.chat_service.Crew", return_value=MagicMock()), \
         patch.object(service, "_run_crew_with_timeout", return_value=make_mock_crew_result()):

        await service.execute_chat_query(
            message="AAPL price?", stock_symbol="AAPL", market="US", job_id="job-xyz"
        )

    mock_job_store.create_job.assert_called_once_with("job-xyz", "chat")
    statuses = [call[0][1] for call in mock_job_store.update_job.call_args_list]
    assert statuses[0] == "processing"
    assert statuses[-1] == "completed"


@pytest.mark.asyncio
async def test_result_contains_response_sources_reasoning(service):
    """Result dict must have response, sources, agent_reasoning populated."""
    crew_result = make_mock_crew_result(
        response="AAPL is at $175 with strong earnings.",
        sources=[Source(title="Reuters", url="https://reuters.com", date="2026-03-29")],
        reasoning="Fetched from yfinance and recent news."
    )
    with patch("app.services.chat_service.classify_intent",
               return_value={"needs_news": False, "needs_metrics": True, "needs_analysis": False, "needs_comparison": False}), \
         patch("app.services.chat_service.FinancialTasks.analyze_stock_financials", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialTasks.synthesize_chat_response", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.market_researcher", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.financial_data_analyst", return_value=MagicMock()), \
         patch("app.services.chat_service.FinancialAgents.investment_advisor", return_value=MagicMock()), \
         patch("app.services.chat_service.Crew", return_value=MagicMock()), \
         patch.object(service, "_run_crew_with_timeout", return_value=crew_result):

        result = await service.execute_chat_query(
            message="AAPL price?", stock_symbol="AAPL", market="US"
        )

    assert result["response"] == "AAPL is at $175 with strong earnings."
    assert len(result["sources"]) == 1
    assert result["agent_reasoning"] == "Fetched from yfinance and recent news."
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_chat_service.py -v
```

Expected: `ImportError: cannot import name 'ChatService' from 'app.services.chat_service'`

- [ ] **Step 3: Create app/services/chat_service.py**

```python
"""
Chat Service — executes the chat crew with intent-driven task selection.
"""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import uuid
from crewai import Crew, Process

from app.crew.agents import FinancialAgents
from app.crew.tasks import FinancialTasks
from app.crew.output_models import ChatAnswerOutput
from app.services.job_store import JobStore
from app.services.intent_classifier import classify_intent
from app.utils.logger import get_logger
from app.utils.exceptions import CrewExecutionError

logger = get_logger(__name__)

CHAT_TIMEOUT = 30


class ChatService:
    """Executes the chat crew asynchronously with intent-driven task selection."""

    def __init__(self, job_store: Optional[JobStore] = None):
        self.job_store = job_store

    async def execute_chat_query(
        self,
        message: str,
        stock_symbol: str,
        market: str,
        job_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute crew for chat endpoint.

        Args:
            message: User's question
            stock_symbol: Stock symbol to analyze
            market: "US" or "IN"
            job_id: Optional job ID for tracking

        Returns:
            Dict with response, sources, agent_reasoning, stock_symbol, timestamp
        """
        if not job_id:
            job_id = str(uuid.uuid4())

        if self.job_store:
            await self.job_store.create_job(job_id, "chat")
            await self.job_store.update_job(job_id, "processing", "Initializing agents...")

        try:
            market_researcher = FinancialAgents.market_researcher()
            data_analyst = FinancialAgents.financial_data_analyst()
            advisor = FinancialAgents.investment_advisor()

            if self.job_store:
                await self.job_store.update_job(job_id, "processing", "Classifying query intent...")

            intent = await classify_intent(message)
            logger.info(f"Classified intent: {intent}")

            tasks = []

            if self.job_store:
                await self.job_store.update_job(job_id, "processing", "Analyzing financial data...")

            if intent["needs_news"]:
                tasks.append(FinancialTasks.research_stock_news(
                    market_researcher, stock_symbol, stock_symbol
                ))

            if intent["needs_metrics"]:
                tasks.append(FinancialTasks.analyze_stock_financials(
                    data_analyst, stock_symbol, market
                ))

            if not tasks:
                tasks.append(FinancialTasks.analyze_stock_financials(
                    data_analyst, stock_symbol, market
                ))

            if self.job_store:
                await self.job_store.update_job(job_id, "processing", "Synthesizing response...")

            tasks.append(FinancialTasks.synthesize_chat_response(
                advisor, message, stock_symbol, market
            ))

            crew = Crew(
                agents=[market_researcher, data_analyst, advisor],
                tasks=tasks,
                process=Process.sequential,
                verbose=True,
                memory=False,
                cache=True,
            )

            result = await self._run_crew_with_timeout(crew, timeout=CHAT_TIMEOUT)

            output: ChatAnswerOutput = result.pydantic
            response_data = {
                "response": output.response,
                "sources": [s.model_dump() for s in output.sources],
                "agent_reasoning": output.agent_reasoning,
                "stock_symbol": stock_symbol,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

            if self.job_store:
                await self.job_store.update_job(
                    job_id, "completed", "Analysis complete", result=response_data
                )

            logger.info(f"Chat query completed for {stock_symbol}")
            return response_data

        except asyncio.TimeoutError:
            error_msg = "Analysis timed out. Please try again."
            logger.error(f"Chat query timeout for {stock_symbol}")
            if self.job_store:
                await self.job_store.update_job(job_id, "failed", error=error_msg)
            raise CrewExecutionError(error_msg)

        except Exception as e:
            error_msg = f"Analysis failed: {str(e)}"
            logger.error(f"Chat query error for {stock_symbol}: {e}", exc_info=True)
            if self.job_store:
                await self.job_store.update_job(job_id, "failed", error=error_msg)
            raise CrewExecutionError(error_msg)

    async def _run_crew_with_timeout(self, crew: Crew, timeout: int):
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, crew.kickoff),
            timeout=timeout
        )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_chat_service.py -v
```

Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/chat_service.py tests/test_chat_service.py
git commit -m "feat: add ChatService with intent-driven crew execution and structured output parsing"
```

---

## Task 8: Create RecommendationsService with tests

**Files:**
- Create: `app/services/recommendations_service.py`
- Create: `tests/test_recommendations_service.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_recommendations_service.py`:

```python
"""Unit tests for RecommendationsService."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.recommendations_service import RecommendationsService
from app.crew.output_models import (
    SectorRankingOutput, SectorInfo,
    SectorStocksOutput, StockPickOutput,
    SectorFundsOutput, FundPickOutput,
)
from app.utils.exceptions import CrewExecutionError


@pytest.fixture
def mock_job_store():
    return AsyncMock()


@pytest.fixture
def service(mock_job_store):
    return RecommendationsService(job_store=mock_job_store)


def make_sector_result(sectors=None):
    mock = MagicMock()
    mock.pydantic = SectorRankingOutput(sectors=sectors or [
        SectorInfo(name="Technology", performance_pct=12.5, trend="Uptrend", momentum="Accelerating", drivers="AI"),
        SectorInfo(name="Healthcare", performance_pct=8.3, trend="Uptrend", momentum="Neutral", drivers="Aging"),
        SectorInfo(name="Financials", performance_pct=6.7, trend="Uptrend", momentum="Decelerating", drivers="Rates"),
    ])
    return mock


def make_stocks_result(sector="Technology", market="US"):
    mock = MagicMock()
    mock.pydantic = SectorStocksOutput(
        sector=sector, market=market,
        stocks=[StockPickOutput(
            symbol="AAPL", company_name="Apple Inc.",
            current_price=175.0, currency="USD",
            change_percent=5.0, recommendation_score=9.0,
            reasoning="Strong fundamentals."
        )]
    )
    return mock


def make_funds_result(sector="Technology", market="US"):
    mock = MagicMock()
    mock.pydantic = SectorFundsOutput(
        sector=sector, market=market,
        funds=[FundPickOutput(
            symbol="XLK", name="Technology Select Sector SPDR",
            current_nav=195.0, currency="USD",
            change_percent=3.2, recommendation_score=8.5,
            reasoning="Top tech ETF."
        )]
    )
    return mock


@pytest.mark.asyncio
async def test_stock_recommendations_sector_crew_runs_first(service):
    """Sector crew must run once before per-sector stock crews (1 + 3 calls total)."""
    results = [make_sector_result()] + [make_stocks_result()] * 3
    service._run_crew_with_timeout = AsyncMock(side_effect=results)

    with patch("app.services.recommendations_service.FinancialAgents.market_researcher", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.financial_data_analyst", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.sector_performance_analyst", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.investment_advisor", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.identify_top_sectors", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.find_top_stocks_in_sector", return_value=MagicMock()), \
         patch("app.services.recommendations_service.Crew", return_value=MagicMock()):

        await service.execute_stock_recommendations(market="US", timeframe="30d")

    assert service._run_crew_with_timeout.call_count == 4  # 1 sector + 3 stocks


@pytest.mark.asyncio
async def test_fund_recommendations_calls_etf_task_not_stock_task(service):
    """Fund recommendations must use identify_top_etfs_in_sector, not find_top_stocks_in_sector."""
    results = [make_sector_result()] + [make_funds_result()] * 3
    service._run_crew_with_timeout = AsyncMock(side_effect=results)

    with patch("app.services.recommendations_service.FinancialAgents.sector_performance_analyst", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.financial_data_analyst", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.investment_advisor", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.identify_top_sectors", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.identify_top_etfs_in_sector", return_value=MagicMock()) as mock_etf, \
         patch("app.services.recommendations_service.FinancialTasks.find_top_stocks_in_sector", return_value=MagicMock()) as mock_stocks, \
         patch("app.services.recommendations_service.Crew", return_value=MagicMock()):

        await service.execute_fund_recommendations(market="US", timeframe="30d")

    mock_etf.assert_called()
    mock_stocks.assert_not_called()


@pytest.mark.asyncio
async def test_all_market_combines_us_and_in(service):
    """ALL market should produce results from both US and IN."""
    us_sector = make_sector_result([
        SectorInfo(name="Technology", performance_pct=12.5, trend="Uptrend", momentum="Accelerating", drivers="AI"),
        SectorInfo(name="Healthcare", performance_pct=8.3, trend="Uptrend", momentum="Neutral", drivers="Aging"),
        SectorInfo(name="Financials", performance_pct=6.7, trend="Uptrend", momentum="Decelerating", drivers="Rates"),
    ])
    in_sector = make_sector_result([
        SectorInfo(name="Banking", performance_pct=10.1, trend="Uptrend", momentum="Accelerating", drivers="Credit"),
        SectorInfo(name="Technology", performance_pct=9.5, trend="Uptrend", momentum="Neutral", drivers="Digital"),
        SectorInfo(name="Pharma", performance_pct=7.8, trend="Uptrend", momentum="Neutral", drivers="Exports"),
    ])
    us_stock = make_stocks_result("Technology", "US")
    in_stock = make_stocks_result("Banking", "IN")

    results = (
        [us_sector] + [us_stock] * 3 +
        [in_sector] + [in_stock] * 3
    )
    service._run_crew_with_timeout = AsyncMock(side_effect=results)

    with patch("app.services.recommendations_service.FinancialAgents.market_researcher", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.financial_data_analyst", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.sector_performance_analyst", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.investment_advisor", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.identify_top_sectors", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.find_top_stocks_in_sector", return_value=MagicMock()), \
         patch("app.services.recommendations_service.Crew", return_value=MagicMock()):

        result = await service.execute_stock_recommendations(market="ALL", timeframe="30d")

    markets = {s["market"] for s in result["top_sectors"]}
    assert "US" in markets
    assert "IN" in markets


@pytest.mark.asyncio
async def test_failed_sector_crew_sets_job_failed(service, mock_job_store):
    """If the sector crew raises, job_store must be updated to 'failed'."""
    service._run_crew_with_timeout = AsyncMock(side_effect=Exception("Sector crew blew up"))

    with patch("app.services.recommendations_service.FinancialAgents.market_researcher", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.financial_data_analyst", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.sector_performance_analyst", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.investment_advisor", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.identify_top_sectors", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.find_top_stocks_in_sector", return_value=MagicMock()), \
         patch("app.services.recommendations_service.Crew", return_value=MagicMock()):

        with pytest.raises(CrewExecutionError):
            await service.execute_stock_recommendations(market="US", timeframe="30d", job_id="fail-job")

    failed_calls = [
        c for c in mock_job_store.update_job.call_args_list
        if len(c[0]) > 1 and c[0][1] == "failed"
    ]
    assert len(failed_calls) == 1


@pytest.mark.asyncio
async def test_stock_result_contains_real_symbol_not_placeholder(service):
    """Top stocks in result must not contain 'STOCK1' placeholder."""
    results = [make_sector_result()] + [make_stocks_result()] * 3
    service._run_crew_with_timeout = AsyncMock(side_effect=results)

    with patch("app.services.recommendations_service.FinancialAgents.market_researcher", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.financial_data_analyst", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.sector_performance_analyst", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.investment_advisor", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.identify_top_sectors", return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.find_top_stocks_in_sector", return_value=MagicMock()), \
         patch("app.services.recommendations_service.Crew", return_value=MagicMock()):

        result = await service.execute_stock_recommendations(market="US", timeframe="30d")

    all_symbols = [
        stock["symbol"]
        for sector in result["top_sectors"]
        for stock in sector["top_stocks"]
    ]
    assert "STOCK1" not in all_symbols
    assert all(len(sym) > 0 for sym in all_symbols)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_recommendations_service.py -v
```

Expected: `ImportError: cannot import name 'RecommendationsService'`

- [ ] **Step 3: Create app/services/recommendations_service.py**

```python
"""
Recommendations Service — executes stock and fund recommendation crews.

Stock recommendations: sector identification crew → per-sector stock picking crew.
Fund recommendations: sector identification crew → per-sector ETF picking crew (separate from stocks).
"""

import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import uuid
from crewai import Crew, Process

from app.crew.agents import FinancialAgents
from app.crew.tasks import FinancialTasks
from app.crew.output_models import SectorRankingOutput, SectorStocksOutput, SectorFundsOutput
from app.services.job_store import JobStore
from app.utils.logger import get_logger
from app.utils.exceptions import CrewExecutionError

logger = get_logger(__name__)

SECTOR_TIMEOUT = 60
STOCK_TIMEOUT = 60
FUND_TIMEOUT = 60


class RecommendationsService:
    """Executes stock and fund recommendation crews with structured output parsing."""

    def __init__(self, job_store: Optional[JobStore] = None):
        self.job_store = job_store

    async def execute_stock_recommendations(
        self,
        market: str,
        timeframe: str,
        job_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute stock recommendation crews.

        Flow per market: identify top sectors → for each sector, find top 3 stocks.

        Args:
            market: "US", "IN", or "ALL"
            timeframe: "7d", "30d", "90d"
            job_id: Job ID for tracking

        Returns:
            Dict with job_id, status, top_sectors (real AI-generated data)
        """
        if not job_id:
            job_id = str(uuid.uuid4())

        if self.job_store:
            await self.job_store.create_job(job_id, "stock_recommendations")
            await self.job_store.update_job(job_id, "processing", "Initializing comprehensive analysis...")

        try:
            market_researcher = FinancialAgents.market_researcher()
            data_analyst = FinancialAgents.financial_data_analyst()
            sector_analyst = FinancialAgents.sector_performance_analyst()
            advisor = FinancialAgents.investment_advisor()

            results: Dict[str, List] = {}
            markets_to_analyze = ["US", "IN"] if market == "ALL" else [market]

            for mkt in markets_to_analyze:
                if self.job_store:
                    await self.job_store.update_job(
                        job_id, "processing", f"Analyzing {mkt} market sectors..."
                    )

                sector_task = FinancialTasks.identify_top_sectors(sector_analyst, mkt, timeframe)
                sector_crew = Crew(
                    agents=[sector_analyst],
                    tasks=[sector_task],
                    process=Process.sequential,
                    verbose=True, memory=False, cache=True,
                )
                sector_result = await self._run_crew_with_timeout(sector_crew, SECTOR_TIMEOUT)
                ranking: SectorRankingOutput = sector_result.pydantic
                top_sectors = ranking.sectors[:3]

                sector_recommendations = []
                for i, sector_info in enumerate(top_sectors, 1):
                    if self.job_store:
                        await self.job_store.update_job(
                            job_id, "processing",
                            f"Finding top stocks in {sector_info.name} sector..."
                        )

                    stock_task = FinancialTasks.find_top_stocks_in_sector(
                        advisor, sector_info.name, mkt, timeframe
                    )
                    stock_crew = Crew(
                        agents=[data_analyst, advisor],
                        tasks=[stock_task],
                        process=Process.sequential,
                        verbose=True, memory=False, cache=True,
                    )
                    stock_result = await self._run_crew_with_timeout(stock_crew, STOCK_TIMEOUT)
                    stocks_output: SectorStocksOutput = stock_result.pydantic

                    sector_recommendations.append({
                        "sector": sector_info.name,
                        "rank": i,
                        "performance_percent": sector_info.performance_pct,
                        "market": mkt,
                        "top_stocks": [s.model_dump() for s in stocks_output.stocks[:3]]
                    })

                results[mkt] = sector_recommendations

            if self.job_store:
                await self.job_store.update_job(
                    job_id, "processing", "Creating final recommendation report..."
                )

            combined: List = []
            for mkt_results in results.values():
                combined.extend(mkt_results)

            final_result = {
                "job_id": job_id,
                "status": "completed",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "timeframe": timeframe,
                "market": market,
                "top_sectors": combined,
                "analysis_summary": (
                    f"Analysis of {market} market over {timeframe} based on real-time "
                    "sector performance data and AI-driven stock selection."
                ),
                "cache_hit": False
            }

            if self.job_store:
                await self.job_store.update_job(
                    job_id, "completed", "Analysis complete", result=final_result
                )

            logger.info(f"Stock recommendations completed: {job_id}")
            return final_result

        except asyncio.TimeoutError:
            error_msg = "Analysis timed out. The market analysis is taking longer than expected."
            logger.error(f"Stock recommendations timeout: {job_id}")
            if self.job_store:
                await self.job_store.update_job(job_id, "failed", error=error_msg)
            raise CrewExecutionError(error_msg)

        except Exception as e:
            error_msg = f"Recommendation analysis failed: {str(e)}"
            logger.error(f"Stock recommendations error {job_id}: {e}", exc_info=True)
            if self.job_store:
                await self.job_store.update_job(job_id, "failed", error=error_msg)
            raise CrewExecutionError(error_msg)

    async def execute_fund_recommendations(
        self,
        market: str,
        timeframe: str,
        job_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute fund/ETF recommendation crews.

        Fully separate from stock recommendations — uses identify_top_etfs_in_sector task
        which targets ETF symbols (XLK, XLF for US; Nifty indices for India).

        Args:
            market: "US", "IN", or "ALL"
            timeframe: "7d", "30d", "90d"
            job_id: Job ID for tracking

        Returns:
            Dict with job_id, status, top_sectors containing real ETF data
        """
        if not job_id:
            job_id = str(uuid.uuid4())

        if self.job_store:
            await self.job_store.create_job(job_id, "fund_recommendations")
            await self.job_store.update_job(
                job_id, "processing", "Analyzing sector ETFs and funds..."
            )

        try:
            sector_analyst = FinancialAgents.sector_performance_analyst()
            data_analyst = FinancialAgents.financial_data_analyst()
            advisor = FinancialAgents.investment_advisor()

            results: Dict[str, List] = {}
            markets_to_analyze = ["US", "IN"] if market == "ALL" else [market]

            for mkt in markets_to_analyze:
                if self.job_store:
                    await self.job_store.update_job(
                        job_id, "processing", f"Analyzing {mkt} market sectors for ETFs..."
                    )

                sector_task = FinancialTasks.identify_top_sectors(sector_analyst, mkt, timeframe)
                sector_crew = Crew(
                    agents=[sector_analyst],
                    tasks=[sector_task],
                    process=Process.sequential,
                    verbose=True, memory=False, cache=True,
                )
                sector_result = await self._run_crew_with_timeout(sector_crew, SECTOR_TIMEOUT)
                ranking: SectorRankingOutput = sector_result.pydantic
                top_sectors = ranking.sectors[:3]

                sector_fund_recommendations = []
                for i, sector_info in enumerate(top_sectors, 1):
                    if self.job_store:
                        await self.job_store.update_job(
                            job_id, "processing",
                            f"Finding top ETFs in {sector_info.name} sector..."
                        )

                    etf_task = FinancialTasks.identify_top_etfs_in_sector(
                        advisor, sector_info.name, mkt, timeframe
                    )
                    etf_crew = Crew(
                        agents=[data_analyst, advisor],
                        tasks=[etf_task],
                        process=Process.sequential,
                        verbose=True, memory=False, cache=True,
                    )
                    etf_result = await self._run_crew_with_timeout(etf_crew, FUND_TIMEOUT)
                    funds_output: SectorFundsOutput = etf_result.pydantic

                    sector_fund_recommendations.append({
                        "sector": sector_info.name,
                        "rank": i,
                        "performance_percent": sector_info.performance_pct,
                        "market": mkt,
                        "top_funds": [f.model_dump() for f in funds_output.funds[:3]]
                    })

                results[mkt] = sector_fund_recommendations

            combined: List = []
            for mkt_results in results.values():
                combined.extend(mkt_results)

            final_result = {
                "job_id": job_id,
                "status": "completed",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "timeframe": timeframe,
                "market": market,
                "top_sectors": combined,
                "analysis_summary": (
                    f"ETF/Fund analysis of {market} market over {timeframe}."
                ),
                "cache_hit": False
            }

            if self.job_store:
                await self.job_store.update_job(
                    job_id, "completed", "Analysis complete", result=final_result
                )

            logger.info(f"Fund recommendations completed: {job_id}")
            return final_result

        except asyncio.TimeoutError:
            error_msg = "Fund analysis timed out."
            logger.error(f"Fund recommendations timeout: {job_id}")
            if self.job_store:
                await self.job_store.update_job(job_id, "failed", error=error_msg)
            raise CrewExecutionError(error_msg)

        except Exception as e:
            error_msg = f"Fund analysis failed: {str(e)}"
            logger.error(f"Fund recommendations error {job_id}: {e}", exc_info=True)
            if self.job_store:
                await self.job_store.update_job(job_id, "failed", error=error_msg)
            raise CrewExecutionError(error_msg)

    async def _run_crew_with_timeout(self, crew: Crew, timeout: int):
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, crew.kickoff),
            timeout=timeout
        )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_recommendations_service.py -v
```

Expected: all 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/recommendations_service.py tests/test_recommendations_service.py
git commit -m "feat: add RecommendationsService with real ETF fund logic and structured output parsing"
```

---

## Task 9: Refactor crew_service.py to thin facade and update __init__.py

**Files:**
- Modify: `app/services/crew_service.py`
- Modify: `app/services/__init__.py`

- [ ] **Step 1: Replace crew_service.py with thin facade**

Replace the entire contents of `app/services/crew_service.py` with:

```python
"""
CrewService — backward-compatible facade over ChatService and RecommendationsService.

Existing consumers (dependencies.py, tests) continue to import CrewService unchanged.
New code should import ChatService or RecommendationsService directly.
"""

from typing import Optional, Dict, Any
from app.services.chat_service import ChatService
from app.services.recommendations_service import RecommendationsService
from app.services.job_store import JobStore
from app.utils.exceptions import CrewExecutionError  # re-export for backward compat


class CrewService:
    """Thin facade combining ChatService and RecommendationsService."""

    def __init__(self, job_store: Optional[JobStore] = None):
        self._chat = ChatService(job_store=job_store)
        self._recommendations = RecommendationsService(job_store=job_store)
        self.job_store = job_store

    async def execute_chat_query(self, *args, **kwargs) -> Dict[str, Any]:
        return await self._chat.execute_chat_query(*args, **kwargs)

    async def execute_stock_recommendations(self, *args, **kwargs) -> Dict[str, Any]:
        return await self._recommendations.execute_stock_recommendations(*args, **kwargs)

    async def execute_fund_recommendations(self, *args, **kwargs) -> Dict[str, Any]:
        return await self._recommendations.execute_fund_recommendations(*args, **kwargs)
```

- [ ] **Step 2: Update app/services/__init__.py to export new services**

Replace the contents of `app/services/__init__.py` with:

```python
from .cache import CacheService, make_chat_cache_key, make_fund_cache_key, make_stock_cache_key, get_cache_bucket
from .job_store import JobStore
from .chat_service import ChatService
from .recommendations_service import RecommendationsService
from .crew_service import CrewService, CrewExecutionError

__all__ = [
    "CacheService",
    "make_chat_cache_key",
    "make_fund_cache_key",
    "make_stock_cache_key",
    "get_cache_bucket",
    "JobStore",
    "ChatService",
    "RecommendationsService",
    "CrewService",
    "CrewExecutionError",
]
```

- [ ] **Step 3: Run the full test suite to confirm no regressions**

```bash
pytest tests/test_crew_service.py tests/test_job_store.py tests/test_output_models.py tests/test_chat_service.py tests/test_recommendations_service.py -v
```

Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add app/services/crew_service.py app/services/__init__.py
git commit -m "refactor: crew_service.py becomes thin facade, export new services from __init__"
```

---

## Task 10: Update existing integration tests

**Files:**
- Modify: `tests/test_chat.py`
- Modify: `tests/test_stocks.py`
- Modify: `tests/test_funds.py`

> These tests require a running server (`uvicorn app.main:app --reload`). Run with `pytest tests/test_chat.py -v` only when the server is up.

- [ ] **Step 1: Read current test_chat.py**

```bash
cat tests/test_chat.py
```

- [ ] **Step 2: Update test_chat.py assertions**

Find all assertions that accept `None` or empty for `agent_reasoning` or `sources` and tighten them. Add a test that a missing `stock_symbol` now returns 400. Replace/update with:

```python
def test_chat_missing_stock_symbol_returns_400(http_client):
    """After fix: stock_symbol is required, no silent AAPL fallback."""
    response = http_client.post("/api/v1/chat", json={"message": "Tell me something"})
    assert response.status_code == 400


def test_chat_response_has_non_empty_response_text(http_client):
    response = http_client.post("/api/v1/chat", json={
        "stock_symbol": "AAPL",
        "message": "What is the current price?"
    })
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["response"], str)
    assert len(data["response"]) > 10


def test_chat_response_has_sources_list(http_client):
    response = http_client.post("/api/v1/chat", json={
        "stock_symbol": "AAPL",
        "message": "What is the current price?"
    })
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["sources"], list)


def test_chat_response_has_agent_reasoning(http_client):
    response = http_client.post("/api/v1/chat", json={
        "stock_symbol": "AAPL",
        "message": "What is the current price?"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["agent_reasoning"] is not None
    assert isinstance(data["agent_reasoning"], str)
```

- [ ] **Step 3: Update test_stocks.py assertions**

Find assertions that check for `"STOCK1"` or hardcoded sectors and replace:

```python
def test_stock_recommendations_result_has_real_symbols(http_client):
    """Completed job must not contain placeholder 'STOCK1' symbol."""
    import time
    # Create job
    create_resp = http_client.post("/api/v1/stocks/recommendations", json={
        "timeframe": "30d", "market": "US"
    })
    assert create_resp.status_code == 200
    job_id = create_resp.json()["job_id"]

    # Poll until completed (max 120s)
    for _ in range(40):
        status_resp = http_client.get(f"/api/v1/stocks/recommendations/{job_id}")
        data = status_resp.json()
        if data["status"] == "completed":
            break
        time.sleep(3)
    else:
        pytest.skip("Job did not complete within 120s — integration test needs running server")

    result = data["result"]
    assert result is not None
    all_symbols = [
        stock["symbol"]
        for sector in result.get("top_sectors", [])
        for stock in sector.get("top_stocks", [])
    ]
    assert "STOCK1" not in all_symbols
    assert len(all_symbols) > 0
```

- [ ] **Step 4: Update test_funds.py assertions**

```python
def test_fund_recommendations_result_differs_from_stock_result(http_client):
    """Fund result must contain top_funds, not top_stocks."""
    import time
    create_resp = http_client.post("/api/v1/funds/recommendations", json={
        "timeframe": "30d", "market": "US"
    })
    assert create_resp.status_code == 200
    job_id = create_resp.json()["job_id"]

    for _ in range(40):
        status_resp = http_client.get(f"/api/v1/funds/recommendations/{job_id}")
        data = status_resp.json()
        if data["status"] == "completed":
            break
        time.sleep(3)
    else:
        pytest.skip("Job did not complete within 120s")

    result = data["result"]
    assert result is not None
    for sector in result.get("top_sectors", []):
        assert "top_funds" in sector, "Fund result must have top_funds, not top_stocks"
        assert "top_stocks" not in sector

def test_fund_result_has_nav_field(http_client):
    """Each fund in result must have current_nav populated."""
    import time
    create_resp = http_client.post("/api/v1/funds/recommendations", json={
        "timeframe": "30d", "market": "US"
    })
    job_id = create_resp.json()["job_id"]

    for _ in range(40):
        status_resp = http_client.get(f"/api/v1/funds/recommendations/{job_id}")
        data = status_resp.json()
        if data["status"] == "completed":
            break
        time.sleep(3)
    else:
        pytest.skip("Job did not complete within 120s")

    result = data["result"]
    for sector in result.get("top_sectors", []):
        for fund in sector.get("top_funds", []):
            assert "current_nav" in fund
            assert isinstance(fund["current_nav"], (int, float))
```

- [ ] **Step 5: Run all unit tests (no server needed)**

```bash
pytest tests/test_job_store.py tests/test_output_models.py tests/test_chat_service.py tests/test_recommendations_service.py tests/test_crew_service.py tests/test_intent_classifier.py -v
```

Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_chat.py tests/test_stocks.py tests/test_funds.py
git commit -m "test: update integration test assertions for structured output and fund separation"
```

---

## Task 11: Final verification

- [ ] **Step 1: Run complete unit test suite**

```bash
pytest tests/test_job_store.py tests/test_output_models.py tests/test_chat_service.py tests/test_recommendations_service.py tests/test_crew_service.py tests/test_intent_classifier.py -v
```

Expected: all tests PASS, no warnings about mutable defaults

- [ ] **Step 2: Start server and run smoke tests**

```bash
# Terminal 1: start Redis
docker run -d -p 6379:6379 redis:7-alpine

# Terminal 2: start server
cd stocks_analyzer_be_01
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

```bash
# Terminal 3: smoke tests
pytest tests/test_health.py -v
```

Expected: health endpoint returns `{"status": "healthy", "redis_status": "connected"}`

- [ ] **Step 3: Verify chat endpoint rejects missing symbol**

```bash
curl -s -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Tell me about Apple"}' | python -m json.tool
```

Expected: `{"detail": "stock_symbol is required...", "error_code": "HTTP_400"}`

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "chore: final backend improvement pass complete"
```

---

## Reference: Run Commands

```bash
# All unit tests (no server needed):
pytest tests/test_job_store.py tests/test_output_models.py tests/test_chat_service.py tests/test_recommendations_service.py tests/test_crew_service.py tests/test_intent_classifier.py -v

# All integration tests (server must be running at localhost:8000):
pytest tests/test_health.py tests/test_chat.py tests/test_stocks.py tests/test_funds.py -v

# Full suite:
pytest tests/ -v
```
