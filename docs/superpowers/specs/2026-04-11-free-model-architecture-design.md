# Architecture Redesign: Free-Model-Compatible Agent Flows

**Date:** 2026-04-11  
**Author:** Aayush Vijayvergiya  
**Status:** Draft — Pending Review  
**Objective:** Redesign all three agent flows (Chat, Stock Recommendations, Fund Recommendations) to work reliably with free-tier OpenRouter models by eliminating iteration starvation, reducing LLM surface area to pure reasoning, and pre-fetching all deterministic data outside the agent loop.

---

## Table of Contents

1. [Background & Diagnosis](#1-background--diagnosis)
2. [Current Architecture — All Flows](#2-current-architecture--all-flows)
   - 2.1 Chat Flow
   - 2.2 Stock Recommendations Flow
   - 2.3 Fund Recommendations Flow
3. [Root Cause Analysis per Flow](#3-root-cause-analysis-per-flow)
4. [Proposed Architecture — All Flows](#4-proposed-architecture--all-flows)
   - 4.1 Chat Flow
   - 4.2 Stock Recommendations Flow
   - 4.3 Fund Recommendations Flow
5. [Cross-Cutting Changes](#5-cross-cutting-changes)
6. [Implementation Checklist](#6-implementation-checklist)

---

## 1. Background & Diagnosis

### The Core Constraint

`meta-llama/llama-4-scout:free` (and free-tier models generally) have three hard limitations compared to GPT-4-class models:

| Limitation | Impact |
|---|---|
| **No reliable structured function calling** | ReAct format bleeds into final answer; `output_pydantic` validation fails |
| **Limited context window (16k)** | Raw DataFrame dumps (`PortfolioDataTool`) and long tool output chains overflow context |
| **Inconsistent JSON output** | Model sometimes outputs trailing chars, misses required fields, or returns partial JSON |

### The Fundamental Design Mismatch

The current architecture gives the LLM **two jobs at once**: (1) drive tool calls to fetch data, and (2) produce structured JSON output. Free models cannot reliably do both in a single task. The result is that the last token before `max_iter` is hit is a ReAct `thought/action` dict, which CrewAI parses against `output_pydantic` and fails.

This was already recognised and fixed for **sector identification** (`_get_top_sectors_direct` bypasses the crew entirely). The fix was not applied consistently to the other data-fetching steps.

### Design Principle for the Redesign

> **The LLM should only be asked to reason over pre-fetched data — never to drive tool calls AND produce structured JSON simultaneously.**

Split every agent task into two phases:
- **Phase 1 — Deterministic Python**: Fetch all data synchronously using yfinance/news APIs. No LLM involved.
- **Phase 2 — LLM reasoning**: Hand the pre-fetched data as plain-text context. The LLM's only job is to rank, reason, and output JSON. Zero tool calls needed. `max_iter=2` is enough.

---

## 2. Current Architecture — All Flows

### 2.1 Chat Flow

**Trigger:** `POST /api/v1/chat` — synchronous, caller blocks until response.

```
┌─────────┐   ┌──────────┐   ┌──────────────┐   ┌─────────────────┐   ┌───────────────┐
│  Client │   │ chat.py  │   │ ChatService  │   │ IntentClassifier│   │   CrewAI Crew │
└────┬────┘   └────┬─────┘   └──────┬───────┘   └────────┬────────┘   └───────┬───────┘
     │              │                │                     │                    │
     │ POST /chat   │                │                     │                    │
     │─────────────>│                │                     │                    │
     │              │ cache check    │                     │                    │
     │              │ (Redis)        │                     │                    │
     │              │──────────────> (cache miss)          │                    │
     │              │                │                     │                    │
     │              │ execute_chat_  │                     │                    │
     │              │ query()        │                     │                    │
     │              │───────────────>│                     │                    │
     │              │                │ classify_intent()   │                    │
     │              │                │────────────────────>│                    │
     │              │                │                     │ OpenRouter API call│
     │              │                │                     │ (llama-3.2-3b)     │
     │              │                │                     │──────────────────> │(external)
     │              │                │                     │<────────────────── │
     │              │                │ intent dict         │                    │
     │              │                │<────────────────────│                    │
     │              │                │                     │                    │
     │              │                │ build tasks (0–2    │                    │
     │              │                │ data tasks +        │                    │
     │              │                │ 1 synthesize task)  │                    │
     │              │                │                     │                    │
     │              │                │ crew.kickoff()      │                    │
     │              │                │────────────────────────────────────────>│
     │              │                │                     │                    │
     │              │                │                     │    [Task 1: optional]
     │              │                │                     │    research_stock_news
     │              │                │                     │    Agent: market_researcher
     │              │                │                     │    max_iter=5
     │              │                │                     │    Tools: WebSearch, NewsAPI
     │              │                │                     │    ─ iter1: WebSearch call
     │              │                │                     │    ─ iter2: NewsAPI call
     │              │                │                     │    ─ iter3: output text
     │              │                │                     │    (free-text output, no pydantic)
     │              │                │                     │
     │              │                │                     │    [Task 2: optional]
     │              │                │                     │    analyze_stock_financials
     │              │                │                     │    Agent: financial_data_analyst
     │              │                │                     │    max_iter=5
     │              │                │                     │    Tools: YFinanceDataTool
     │              │                │                     │    ─ iter1: fetch price
     │              │                │                     │    ─ iter2: fetch metrics
     │              │                │                     │    ─ iter3: fetch info
     │              │                │                     │    ─ iter4: fetch history
     │              │                │                     │    ─ iter5: output text (MAX HIT possible)
     │              │                │                     │    (free-text output, no pydantic)
     │              │                │                     │
     │              │                │                     │    [Task 3: always]
     │              │                │                     │    synthesize_chat_response
     │              │                │                     │    Agent: investment_advisor
     │              │                │                     │    max_iter=3
     │              │                │                     │    output_pydantic=ChatAnswerOutput
     │              │                │                     │    context=[task1, task2]
     │              │                │                     │    ─ iter1: reads context
     │              │                │                     │    ─ iter2: outputs JSON (maybe)
     │              │                │                     │    ─ iter3: JSON with errors (MAX HIT)
     │              │                │                     │
     │              │                │ result.pydantic     │                    │
     │              │                │<────────────────────────────────────────│
     │              │                │ (may be None or ValidationError)        │
     │              │                │                     │                    │
     │              │ ChatResponse   │                     │                    │
     │<─────────────│                │                     │                    │
```

**Problems:**
- `analyze_stock_financials` makes 3–4 separate `YFinanceDataTool` calls in sequence, burning all 5 iterations before output
- `synthesize_chat_response` with `output_pydantic=ChatAnswerOutput` and `max_iter=3` — the advisor must both read context AND output valid JSON in ≤3 steps, which fails when context is long
- `result.pydantic` is accessed without null-check → `AttributeError` if parsing silently returns `None`
- Chat is synchronous (blocks the HTTP worker thread for 10–90 seconds) — no job polling, no timeout UX

---

### 2.2 Stock Recommendations Flow

**Trigger:** `POST /api/v1/stocks/recommendations` → async background job, polled via `GET /{job_id}`.

```
┌─────────┐  ┌──────────┐  ┌───────────────────────┐  ┌────────────────────────────────────────┐
│ Client  │  │stocks.py │  │  RecommendationsService│  │            CrewAI Crews                │
└────┬────┘  └────┬─────┘  └──────────┬────────────┘  └────────────────────┬───────────────────┘
     │             │                   │                                     │
     │ POST /recs  │                   │                                     │
     │────────────>│                   │                                     │
     │             │ cache check       │                                     │
     │             │ (cache miss)      │                                     │
     │             │ create_job(Redis) │                                     │
     │             │ background_task() │                                     │
     │<────────────│ 200 {job_id,      │                                     │
     │  pending    │      pending}     │                                     │
     │             │                   │                                     │
     │ [background task starts]        │                                     │
     │             │ execute_stock_recs│                                     │
     │             │ (market, timeframe│                                     │
     │             │  job_id)          │                                     │
     │             │──────────────────>│                                     │
     │             │                   │                                     │
     │             │                   │ _get_top_sectors_direct()           │
     │             │                   │ [Python/yfinance, NO LLM]           │
     │             │                   │──────────────────> (yfinance.history)
     │             │                   │<────────────────── SectorRankingOutput
     │             │                   │                                     │
     │             │                   │ asyncio.gather(3 sector crews)      │
     │             │                   │─────────────────────────────────────>
     │             │                   │                                     │
     │             │                   │  [Sector Crew 1 — concurrent]       │
     │             │                   │  Crew: [data_analyst, advisor]      │
     │             │                   │  Tasks: [find_top_stocks,           │
     │             │                   │          reflect_on_picks]          │
     │             │                   │                                     │
     │             │                   │  Task: find_top_stocks_in_sector    │
     │             │                   │  Agent: financial_data_analyst      │
     │             │                   │  max_iter=5, output_pydantic=       │
     │             │                   │            SectorStocksOutput       │
     │             │                   │  ─ iter1: SectorStocksMapperTool    │
     │             │                   │          → 10 stock symbols         │
     │             │                   │  ─ iter2: YFinanceDataTool(stock1)  │
     │             │                   │  ─ iter3: YFinanceDataTool(stock2)  │
     │             │                   │  ─ iter4: YFinanceDataTool(stock3)  │
     │             │                   │  ─ iter5: YFinanceDataTool(stock4)  │
     │             │                   │          MAX HIT — last output is   │
     │             │                   │          {thought:.., action:..}    │
     │             │                   │          → ValidationError raised   │
     │             │                   │                                     │
     │             │                   │  [Same failure for Sector 2, 3]     │
     │             │                   │                                     │
     │             │                   │<──── all 3 raise ValidationError    │
     │             │                   │                                     │
     │             │                   │ "All sector analyses failed" error  │
     │             │                   │ job_store.update(failed)            │
     │             │                   │                                     │
     │ GET /recs/{id}                  │                                     │
     │────────────>│                   │                                     │
     │<────────────│                   │                                     │
     │  {status:   │                   │                                     │
     │   "failed"} │                   │                                     │
```

**Problems:**
- `find_top_stocks_in_sector` uses `output_pydantic` AND requires tool calls: mathematically impossible in `max_iter=5`
- `reflect_on_stock_picks` also has `output_pydantic=SectorStocksOutput` AND `max_iter=3` — redundant failure point
- 3 concurrent sector crews × 2 tasks each = 6 LLM sessions running simultaneously on a free-tier rate-limited endpoint → rate limit exhaustion
- `PortfolioDataTool` dumps raw DataFrames as strings → context overflow
- No retry on individual sector failure — one bad iteration = sector lost

---

### 2.3 Fund Recommendations Flow

**Trigger:** `POST /api/v1/funds/recommendations` → async background job.

```
┌─────────┐  ┌─────────┐  ┌───────────────────────┐  ┌────────────────────────────────────────┐
│ Client  │  │funds.py │  │  RecommendationsService│  │            CrewAI Crews                │
└────┬────┘  └────┬────┘  └──────────┬────────────┘  └────────────────────┬───────────────────┘
     │            │                   │                                     │
     │ POST /recs │                   │                                     │
     │───────────>│                   │                                     │
     │            │ cache check       │                                     │
     │            │ (cache miss)      │                                     │
     │            │ create_job(Redis) │                                     │
     │<───────────│ 200 {job_id,      │                                     │
     │  pending   │      pending}     │                                     │
     │            │                   │                                     │
     │ [background task starts]       │                                     │
     │            │ execute_fund_recs │                                     │
     │            │──────────────────>│                                     │
     │            │                   │                                     │
     │            │                   │ _get_top_sectors_direct()           │
     │            │                   │ [Python/yfinance, NO LLM]           │
     │            │                   │──────── yfinance fetch ─────────>   │
     │            │                   │<─────── SectorRankingOutput ──────  │
     │            │                   │                                     │
     │            │                   │ asyncio.gather(3 fund crews)        │
     │            │                   │─────────────────────────────────────>
     │            │                   │                                     │
     │            │                   │  [Fund Crew per sector — concurrent]│
     │            │                   │  Task: identify_top_etfs_in_sector  │
     │            │                   │  Agent: financial_data_analyst      │
     │            │                   │  max_iter=5, output_pydantic=       │
     │            │                   │            SectorFundsOutput        │
     │            │                   │  ─ iter1: YFinanceDataTool(ETF1)    │
     │            │                   │  ─ iter2: YFinanceDataTool(ETF2)    │
     │            │                   │  ─ iter3: YFinanceDataTool(ETF3)    │
     │            │                   │  ─ iter4: reasoning step            │
     │            │                   │  ─ iter5: JSON output (sometimes)   │
     │            │                   │           OR: MAX HIT               │
     │            │                   │           → ValidationError         │
     │            │                   │                                     │
     │            │                   │  Task: reflect_on_fund_picks        │
     │            │                   │  Agent: investment_advisor          │
     │            │                   │  max_iter=3, output_pydantic=       │
     │            │                   │            SectorFundsOutput        │
     │            │                   │  (often never reached if task1 fails)
     │            │                   │                                     │
     │            │                   │<──── ValidationErrors / None        │
     │            │                   │                                     │
     │            │                   │ "All fund sector analyses failed"   │
     │            │                   │ job_store.update(failed)            │
```

**Problems:** Same iteration starvation as stocks. Additionally, the ETF task has a slightly better chance because it needs fewer tool calls (3 ETFs vs 5 stocks), but still fails under rate-limited conditions.

---

## 3. Root Cause Analysis per Flow

### Summary Table

| Flow | Primary Failure | Secondary Failure | Tertiary |
|---|---|---|---|
| **Chat** | `synthesize_chat_response` may fail if prior tasks hit `max_iter` and output is malformed | `result.pydantic` null not guarded | Synchronous — 90s HTTP block |
| **Stock Recs** | `find_top_stocks_in_sector`: `max_iter=5` < steps required (6–7) | `reflect_on_stock_picks`: `output_pydantic` + `max_iter=3` is impossible | 6 concurrent LLM sessions → rate limit |
| **Fund Recs** | `identify_top_etfs_in_sector`: same iteration starvation | `reflect_on_fund_picks`: same | 6 concurrent sessions |

### Why `max_iter=5` Is Not Enough for Stocks

```
Required steps for find_top_stocks_in_sector:

  iter 1: SectorStocksMapperTool (get symbol list for sector)
  iter 2: YFinanceDataTool(symbol_1) — fetch price + metrics + info
  iter 3: YFinanceDataTool(symbol_2)
  iter 4: YFinanceDataTool(symbol_3)
  iter 5: YFinanceDataTool(symbol_4)  ← MAX_ITER HIT HERE
  iter 6: [never reached] Reason about data, output JSON

Result: final answer = {thought: "Need to fetch symbol_5...", action: "YFinanceDataTool", ...}
CrewAI tries: SectorStocksOutput(**that_dict) → ValidationError: sector, market, stocks required
```

### The Sector Fix Already Shows the Right Pattern

`_get_top_sectors_direct` (added earlier) proves the approach works:
```
Old: Sector identification crew → LLM calls SectorPerformanceTool → outputs SectorRankingOutput
                                   (often fails — model outputs ReAct step as final answer)

New: _fetch_sectors_sync() → Python calls yfinance directly → constructs SectorRankingOutput
     (always works — deterministic, no LLM)
```

The redesign applies this pattern to **every** data-fetch step across all three flows.

---

## 4. Proposed Architecture — All Flows

### Design Principles Applied

1. **Pre-fetch everything**: All yfinance/API data fetched in Python before any LLM is invoked
2. **LLM gets pre-formatted context, no tools**: Agent `description` includes pre-fetched data as a structured text block. Zero tool calls required.
3. **`max_iter=2` for all synthesis tasks**: 1 iteration to reason, 1 to output JSON. Enough for any free model.
4. **`output_pydantic` only on the final task**: Remove it from intermediate tasks that will never reach the JSON output step
5. **Remove the reflect task**: The "reflect/verify" pattern requires additional tool calls that free models cannot make reliably. Replace with a single well-prompted synthesis task
6. **Null-guard `result.pydantic`** with raw fallback everywhere
7. **Serialise sector crews** (sequential not parallel) for free tier to avoid rate limit exhaustion

---

### 4.1 Chat Flow (Proposed)

**Key changes:**
- Pre-fetch stock metrics in Python (`_fetch_stock_data_sync`) before crew starts
- Pre-fetch news headlines via NewsAPI/Serper in Python (if `needs_news`)
- `synthesize_chat_response` receives all data as plain-text context, no tool calls, `max_iter=2`
- Remove `market_researcher` and `financial_data_analyst` agents from chat crew — only `investment_advisor` needed for synthesis
- Chat stays synchronous (acceptable at 5–15s with no tool calls in LLM phase)

```
┌─────────┐  ┌──────────┐  ┌───────────────────────────────────────────────────────────────┐
│ Client  │  │ chat.py  │  │                        ChatService (proposed)                  │
└────┬────┘  └────┬─────┘  └──────────────────────────────────┬────────────────────────────┘
     │             │                                            │
     │ POST /chat  │                                            │
     │────────────>│                                            │
     │             │ cache check (Redis)                        │
     │             │──────────────────────────────────────────> cache miss
     │             │                                            │
     │             │ execute_chat_query()                       │
     │             │───────────────────────────────────────────>│
     │             │                                            │
     │             │                           classify_intent()│ [unchanged]
     │             │                           (OpenRouter,     │
     │             │                            llama-3.2-3b,   │
     │             │                            ~200ms)         │
     │             │                                            │
     │             │              [PHASE 1 — Pure Python, no LLM]
     │             │                                            │
     │             │                    _fetch_stock_data_sync()│
     │             │                    yfinance.Ticker(symbol) │
     │             │                    → price, pe, eps, roe,  │
     │             │                      marketCap, 30d history│
     │             │                    (always succeeds or     │
     │             │                     returns partial data)  │
     │             │                                            │
     │             │              if needs_news:                │
     │             │                    _fetch_news_sync()      │
     │             │                    NewsAPI/Serper call     │
     │             │                    → top 5 headlines       │
     │             │                    (graceful empty if fails)
     │             │                                            │
     │             │              [PHASE 2 — Single LLM task]  │
     │             │                                            │
     │             │                    build synthesize task   │
     │             │                    description includes    │
     │             │                    pre-fetched data block: │
     │             │                    "Stock: AAPL            │
     │             │                     Price: $175.50         │
     │             │                     P/E: 28.5, ROE: 35%    │
     │             │                     Headlines: [...]       │
     │             │                     User question: ..."    │
     │             │                                            │
     │             │                    Crew([advisor],         │
     │             │                         [synthesize_task], │
     │             │                         max_iter=2,        │
     │             │                         tools=[])          │
     │             │                    → output_pydantic=      │
     │             │                      ChatAnswerOutput      │
     │             │                                            │
     │             │                    crew.kickoff()          │
     │             │                    LLM sees: data already  │
     │             │                    present, just output JSON│
     │             │                    iter1: reads context    │
     │             │                    iter2: outputs JSON ✓   │
     │             │                                            │
     │             │              null-guard result.pydantic    │
     │             │              → raw fallback if needed      │
     │             │                                            │
     │             │ ChatResponse                               │
     │<────────────│                                            │
```

**Expected improvement:** Chat latency drops from 30–90s (with tool call iterations) to 5–15s (single LLM pass over pre-fetched data). Reliability goes from ~40% to ~95% on free models.

---

### 4.2 Stock Recommendations Flow (Proposed)

**Key changes:**
- `_fetch_sector_stocks_sync(sector, market, timeframe)` pre-fetches top-5 stocks with full metrics in Python
- `find_top_stocks_in_sector` is rewritten to embed pre-fetched data in description, no tools, `max_iter=2`
- `reflect_on_stock_picks` is **removed** entirely — replaced by a single well-prompted task
- Sector crews serialised (one at a time) instead of parallel to avoid rate limits on free tier
- `output_pydantic` only on the single LLM task per sector

```
┌─────────┐  ┌──────────┐  ┌──────────────────────────────────────────────────────────────────┐
│ Client  │  │stocks.py │  │              RecommendationsService (proposed)                    │
└────┬────┘  └────┬─────┘  └────────────────────────┬─────────────────────────────────────────┘
     │             │                                  │
     │ POST /recs  │                                  │
     │────────────>│ cache check → miss               │
     │             │ create_job(Redis)                 │
     │<────────────│ {job_id, pending}                │
     │             │                                  │
     │ [background task]                              │
     │             │                                  │
     │             │ execute_stock_recommendations()  │
     │             │─────────────────────────────────>│
     │             │                                  │
     │             │         [PHASE 1 — Pure Python]  │
     │             │                                  │
     │             │         _get_top_sectors_direct()│ [unchanged — already works]
     │             │         yfinance batch fetch     │
     │             │         → SectorRankingOutput    │
     │             │         top_sectors[:3]          │
     │             │                                  │
     │             │         [PHASE 2 — Sequential sector analysis]
     │             │         (serialised, not parallel, to respect free-tier rate limits)
     │             │                                  │
     │             │         for sector in top_sectors:
     │             │           │                      │
     │             │           │  [Python pre-fetch]  │
     │             │           │  _fetch_sector_stocks_sync(sector, market, timeframe)
     │             │           │  For each of top-5 stocks in sector:
     │             │           │    yfinance.Ticker(symbol).info
     │             │           │    → {symbol, name, price, currency,
     │             │           │        change_pct, pe, eps, roe,
     │             │           │        market_cap, debt_to_equity}
     │             │           │  Returns: List[StockDataDict] (5 items)
     │             │           │  (if yfinance fails for a stock: skip it,
     │             │           │   continue with remaining)
     │             │           │                      │
     │             │           │  [Single LLM Task]   │
     │             │           │  find_top_stocks_in_sector(
     │             │           │    agent=data_analyst,
     │             │           │    prefetched_stocks=stock_data,
     │             │           │    sector, market, timeframe
     │             │           │  )
     │             │           │  description embeds full data table:
     │             │           │  "Here are 5 stocks in {sector}:
     │             │           │   1. AAPL - $175, P/E: 28.5, ROE: 35%...
     │             │           │   2. MSFT - $380, P/E: 35.1, ROE: 40%...
     │             │           │   [...]
     │             │           │   Rank top 3. Output JSON only."
     │             │           │                      │
     │             │           │  Crew([data_analyst],│
     │             │           │      [stock_task],   │
     │             │           │      tools=[],       │
     │             │           │      max_iter=2)     │
     │             │           │  output_pydantic=    │
     │             │           │    SectorStocksOutput│
     │             │           │                      │
     │             │           │  iter1: reads table  │
     │             │           │  iter2: outputs JSON ✓
     │             │           │                      │
     │             │           │  null-guard + raw    │
     │             │           │  fallback            │
     │             │           │                      │
     │             │         end for                  │
     │             │                                  │
     │             │         combined results         │
     │             │         job_store.update(completed)
     │             │         cache.set(result)        │
     │             │                                  │
     │ GET /recs/{id}                                 │
     │────────────>│ job_store.get(job_id)            │
     │<────────────│ {status: completed, result: ...} │
```

**Expected improvement:** Reliability goes from ~0% (all sectors consistently fail) to ~90%+ (single LLM pass per sector with pre-fetched data).

**Trade-off:** Serialised sector analysis adds ~3–5s per sector vs parallel. For a free tier model, this is acceptable — parallel execution was causing rate-limit exhaustion anyway.

---

### 4.3 Fund Recommendations Flow (Proposed)

**Key changes:**
- `_fetch_sector_etfs_sync(sector, market, timeframe)` pre-fetches ETF/index data in Python
- `identify_top_etfs_in_sector` rewritten with pre-fetched data, no tools, `max_iter=2`
- `reflect_on_fund_picks` removed — single well-prompted task is enough
- Serialised execution same as stocks

```
┌─────────┐  ┌─────────┐  ┌──────────────────────────────────────────────────────────────────┐
│ Client  │  │funds.py │  │              RecommendationsService (proposed)                    │
└────┬────┘  └────┬────┘  └────────────────────────┬─────────────────────────────────────────┘
     │            │                                 │
     │ POST /recs │                                 │
     │───────────>│ cache check → miss              │
     │            │ create_job(Redis)               │
     │<───────────│ {job_id, pending}               │
     │            │                                 │
     │ [background task]                            │
     │            │                                 │
     │            │ execute_fund_recommendations()  │
     │            │────────────────────────────────>│
     │            │                                 │
     │            │         [PHASE 1 — Pure Python] │
     │            │                                 │
     │            │         _get_top_sectors_direct()  [unchanged]
     │            │         → SectorRankingOutput   │
     │            │         top_sectors[:3]         │
     │            │                                 │
     │            │         [PHASE 2 — Sequential sector ETF analysis]
     │            │                                 │
     │            │         for sector in top_sectors:
     │            │           │                     │
     │            │           │  [Python pre-fetch] │
     │            │           │  _fetch_sector_etfs_sync(sector, market, timeframe)
     │            │           │  primary_etf = etf_map[sector]
     │            │           │  candidates = [primary_etf] + 2 alternatives
     │            │           │  For each ETF symbol:
     │            │           │    ticker.info → {name, expense_ratio, aum}
     │            │           │    ticker.history(period) → change_pct, current_nav
     │            │           │  Returns: List[ETFDataDict] (2–3 items)
     │            │           │                     │
     │            │           │  [Single LLM Task]  │
     │            │           │  identify_top_etfs_in_sector(
     │            │           │    agent=data_analyst,
     │            │           │    prefetched_etfs=etf_data,
     │            │           │    sector, market
     │            │           │  )
     │            │           │  description:
     │            │           │  "Here are ETFs for {sector} in {market}:
     │            │           │   1. XLK - NAV: $195, exp: 0.13%, +3.2%...
     │            │           │   2. VGT  - NAV: $450, exp: 0.10%, +2.8%...
     │            │           │   3. QQQ  - NAV: $390, exp: 0.20%, +3.5%...
     │            │           │   Rank and explain top 3. Output JSON only."
     │            │           │                     │
     │            │           │  Crew([data_analyst],
     │            │           │      [etf_task],    │
     │            │           │      tools=[],      │
     │            │           │      max_iter=2)    │
     │            │           │  output_pydantic=   │
     │            │           │    SectorFundsOutput│
     │            │           │                     │
     │            │           │  null-guard + raw   │
     │            │           │  fallback           │
     │            │           │                     │
     │            │         end for                 │
     │            │                                 │
     │            │         job_store.update(completed)
     │            │         cache.set(result)       │
     │            │                                 │
     │ GET /recs/{id}                               │
     │───────────>│ {status: completed, result: ...}│
```

---

## 5. Cross-Cutting Changes

### 5.1 New Python Data-Fetch Functions

These all live in `recommendations_service.py` and `chat_service.py`. They are plain synchronous functions, wrapped in `loop.run_in_executor` for async compatibility.

```
_fetch_stock_data_sync(symbol: str, timeframe: str) -> dict
  Used by: ChatService
  Fetches: currentPrice, currency, change_pct (over timeframe), trailingPE,
           trailingEps, returnOnEquity, marketCap, debtToEquity, longName

_fetch_sector_stocks_sync(sector: str, market: str, timeframe: str) -> List[dict]
  Used by: RecommendationsService (stocks)
  For each of top-5 symbols from SectorStocksMapperTool._get_sector_stocks():
    Fetches: same fields as above + sector, industry
  Returns partial list if some symbols fail yfinance

_fetch_sector_etfs_sync(sector: str, market: str, timeframe: str) -> List[dict]
  Used by: RecommendationsService (funds)
  primary + 2 alternative ETFs for the sector
  Fetches: currentPrice/nav, change_pct, expenseRatio, totalAssets, longName
```

### 5.2 Task Signature Changes

```
# CURRENT (broken)
find_top_stocks_in_sector(agent, sector, market, timeframe) -> Task
  # agent must call tools internally

# PROPOSED (fixed)
find_top_stocks_in_sector(agent, sector, market, timeframe, prefetched_stocks: List[dict]) -> Task
  # agent receives data in description, no tools, max_iter=2

# Same pattern for:
identify_top_etfs_in_sector(agent, sector, market, timeframe, prefetched_etfs: List[dict]) -> Task
synthesize_chat_response(agent, message, stock_symbol, market, prefetched_data: dict, news: List[dict]) -> Task
```

### 5.3 Agent Changes

```
financial_data_analyst:
  REMOVE tools=[YFinanceDataTool(), PortfolioDataTool()]
         (tools are no longer needed — data pre-fetched)
  SET    max_iter=2  (was 5)

investment_advisor:
  REMOVE tools=[WebSearchTool, NewsAPITool, YFinanceDataTool, ...]
         (synthesiser has no tools — works from provided context)
  SET    max_iter=2  (was 3)

market_researcher (chat only):
  REMOVE from chat crew entirely
  KEEP   for potential future standalone news-only tasks
```

### 5.4 Removed Tasks

| Task | Reason |
|---|---|
| `reflect_on_stock_picks` | Requires tool calls the advisor cannot make in `max_iter=3`. Quality validation moves to the Python pre-fetch layer (filter out stocks with missing critical metrics) |
| `reflect_on_fund_picks` | Same reason |
| `identify_top_sectors` (crew task) | Already replaced by `_get_top_sectors_direct` |

### 5.5 Concurrency Model Change (Stock/Fund Recs)

```
CURRENT:
  asyncio.gather(sector_crew_1, sector_crew_2, sector_crew_3)
  → 3 concurrent LLM sessions → rate limit exhaustion on free tier

PROPOSED:
  for sector in top_sectors:
      result = await _run_stock_crew_for_sector(sector, ...)
  → sequential, 1 LLM session at a time
  → ~10-15s additional latency, but near-100% success vs 0%
```

This is configurable: add a `PARALLEL_SECTOR_ANALYSIS: bool` setting (default `False` for free tier, `True` for paid models).

### 5.6 `result.pydantic` Null Guard (Already Applied)

The null guard + raw JSON fallback in `_run_stock_crew_for_sector` and `_run_fund_crew_for_sector` stays in place as a safety net even after the redesign. Defense-in-depth.

---

## 6. Implementation Checklist

### Phase 1 — Data Fetch Layer (no LLM changes)
- [ ] Add `_fetch_stock_data_sync(symbol, timeframe)` to `recommendations_service.py`
- [ ] Add `_fetch_sector_stocks_sync(sector, market, timeframe)` to `recommendations_service.py`
- [ ] Add `_fetch_sector_etfs_sync(sector, market, timeframe)` to `recommendations_service.py`
- [ ] Add `_fetch_stock_data_sync` and `_fetch_news_sync` to `chat_service.py`
- [ ] Add unit tests for each fetch function (mock yfinance, verify output schema)

### Phase 2 — Task Redesign
- [ ] Rewrite `find_top_stocks_in_sector(agent, ..., prefetched_stocks)` — embed data in description, remove tool calls
- [ ] Rewrite `identify_top_etfs_in_sector(agent, ..., prefetched_etfs)` — same
- [ ] Rewrite `synthesize_chat_response(agent, ..., prefetched_data, news)` — same
- [ ] Delete `reflect_on_stock_picks` task
- [ ] Delete `reflect_on_fund_picks` task
- [ ] Add unit tests for new task descriptions (verify data is embedded, verify no tool calls)

### Phase 3 — Agent Simplification
- [ ] Remove tools from `financial_data_analyst`, set `max_iter=2`
- [ ] Remove tools from `investment_advisor`, set `max_iter=2`
- [ ] Remove `market_researcher` from chat crew (keep definition, remove from chat flow)
- [ ] Update agent tests

### Phase 4 — Service Wiring
- [ ] Update `_run_stock_crew_for_sector`: call `_fetch_sector_stocks_sync` before crew, pass to task
- [ ] Update `_run_fund_crew_for_sector`: call `_fetch_sector_etfs_sync` before crew, pass to task
- [ ] Change sector analysis from `asyncio.gather` to sequential `for` loop
- [ ] Add `PARALLEL_SECTOR_ANALYSIS` config setting
- [ ] Update `execute_chat_query`: call `_fetch_stock_data_sync` + optional `_fetch_news_sync`, pass to task, remove multi-agent crew
- [ ] Update all tests to cover new pre-fetch paths

### Phase 5 — Verification
- [ ] Run full unit test suite — all should pass
- [ ] Manual test: Chat endpoint with `needs_metrics` intent
- [ ] Manual test: Chat endpoint with `needs_news` intent
- [ ] Manual test: Stock recommendations for `US` market
- [ ] Manual test: Stock recommendations for `IN` market
- [ ] Manual test: Fund recommendations for `US` market
- [ ] Verify job polling works end-to-end
- [ ] Check logs show no `ValidationError` or `max_iter` exhaustion warnings

---

## Appendix: Before/After Comparison

| Metric | Current | Proposed |
|---|---|---|
| Chat latency (p50) | 30–90s | 5–15s |
| Stock recs success rate (free model) | ~0% | ~90%+ |
| Fund recs success rate (free model) | ~30% (fewer tool calls) | ~90%+ |
| LLM calls per sector analysis | 6–10 (tool calls + synthesis) | 1 (synthesis only) |
| LLM calls per chat request | 5–12 | 1–2 |
| `max_iter` needed | 5+ (never enough) | 2 (always enough) |
| Parallel LLM sessions | 3 (rate limit risk) | 1 (sequential) |
| `output_pydantic` failure points | 2 per sector crew | 1 per sector crew |
