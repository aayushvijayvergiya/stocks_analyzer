# Parallel Fan-out + Hierarchical Process + Reflection Design
**Date:** 2026-04-03
**Scope:** `stocks_analyzer_be_02` — agentic pattern upgrade for quality and speed
**API contracts:** No breaking changes to existing endpoints or response shapes

---

## 1. Problem Statement

The current `RecommendationsService` has two structural bottlenecks:

| Bottleneck | Current Behaviour | Impact |
|---|---|---|
| **Sequential sector crews** | Sector 1 → Sector 2 → Sector 3 (one at a time) | `ALL` market worst-case: ~480s wall clock |
| **Flat sequential process** | `Process.sequential` — advisor gets pre-baked analyst output | Advisor cannot interrogate, re-query, or correct analysts |
| **No self-critique** | Advisor synthesizes once with no review pass | Hallucinated tickers, weak reasoning go undetected |

---

## 2. Solution Overview

Three targeted changes, each independently deployable:

1. **Parallel fan-out** — `asyncio.gather()` across per-sector stock/fund crews
2. **Hierarchical process** — Investment Advisor becomes manager; Data Analyst is a worker it can re-query
3. **Reflection task** — A second task where the Advisor critiques and refines its own picks before finalising

---

## 3. Change 1 — Parallel Fan-out

### What changes

In `recommendations_service.py`, the per-sector loop:

```python
# BEFORE: sequential
for sector_info in top_sectors:
    result = await self._run_crew_with_timeout(crew, STOCK_TIMEOUT)
```

becomes a parallel gather:

```python
# AFTER: parallel
coros = [
    self._run_stock_crew_for_sector(sector_info, mkt, timeframe)
    for sector_info in top_sectors
]
results = await asyncio.gather(*coros, return_exceptions=True)
```

Additionally, the US and IN sector identification crews (currently sequential) also run in parallel when `market == "ALL"`:

```python
market_coros = [
    self._run_market_analysis(mkt, timeframe, job_id)
    for mkt in markets_to_analyze
]
market_results = await asyncio.gather(*market_coros, return_exceptions=True)
```

### Agent instantiation

Each concurrent crew must own its own agent instances. The per-sector helper method creates fresh `data_analyst` and `advisor` instances — they are not shared across concurrent invocations.

### Partial failure handling

`asyncio.gather(return_exceptions=True)` allows one sector to fail without killing the rest. Failed sectors log a warning and are excluded from results. If ALL sectors fail, the job raises `CrewExecutionError`.

### Timeout adjustment

`STOCK_TIMEOUT` and `FUND_TIMEOUT` increase from 60s → 90s to accommodate the reflection task (Change 3). Wall-clock time for `ALL` market drops from ~480s to ~150s.

**Wall-clock comparison (ALL market, stocks):**

| Step | Before | After |
|---|---|---|
| US sector identification | 60s | 60s (parallel with IN) |
| IN sector identification | 60s | — (runs with US) |
| Stock crews (6 total) | 6 × 60s = 360s | parallel, 90s each = 90s |
| **Total** | **~480s** | **~150s** |

---

## 4. Change 2 — Hierarchical Process

### What changes

Stock and fund picking crews switch from `Process.sequential` to `Process.hierarchical`, with Investment Advisor as `manager_agent`:

```python
# BEFORE
Crew(
    agents=[data_analyst, advisor],
    tasks=[stock_task],
    process=Process.sequential,
)

# AFTER
Crew(
    agents=[data_analyst],           # workers only
    tasks=[stock_task, reflect_task],
    process=Process.hierarchical,
    manager_agent=advisor,            # Investment Advisor manages
    memory=True,                      # advisor retains context across tasks
)
```

### Why this improves quality

In `Process.sequential`, the advisor receives whatever the data analyst produced and synthesises from it once. In `Process.hierarchical`, the advisor:
- Plans how to achieve the task
- Delegates specific sub-questions to the data analyst (e.g. "fetch P/E and ROE for NVDA")
- Can re-query if the response is incomplete
- Only finalises when it has the data it needs

Investment Advisor already has `allow_delegation=True` — no agent changes required.

### Memory

`memory=True` is set on hierarchical crews so the advisor retains intermediate findings across its planning and delegation steps within a single crew run. This is scoped to the crew lifetime (not cross-request).

### Scope

Hierarchical process applies only to the **stock and fund picking crews**. The sector identification crew (single agent, single task) stays as `Process.sequential` — there is no benefit in adding a manager for a solo agent.

---

## 5. Change 3 — Reflection Task

### New task: `reflect_on_stock_picks`

Added to `tasks.py`:

```python
@staticmethod
def reflect_on_stock_picks(agent, sector: str, market: str, context_tasks: list) -> Task:
    return Task(
        description=f"""Review the stock picks for the {sector} sector ({market} market).

        For each recommended stock, verify:
        1. Is the ticker symbol a real, actively traded symbol on the correct exchange?
        2. Is each metric (P/E, ROE, market cap) an actual fetched value, not an estimate?
        3. Is the recommendation_score (0–10) justified by the data — not inflated?
        4. Does the reasoning cite specific numbers, not vague generalities?

        Replace any pick that fails these checks with the next best alternative.
        Output the final verified list of top 3 stocks with complete data.
        """,
        expected_output="Verified, evidence-backed SectorStocksOutput with 3 stocks",
        agent=agent,
        output_pydantic=SectorStocksOutput,
        context=context_tasks,
    )
```

An equivalent `reflect_on_fund_picks` task is added for the fund flow.

### Why `context=context_tasks`

The reflection task receives the stock picking task as context, giving the advisor direct access to the initial output. The advisor does not need to re-run tools — it critiques what the data analyst already produced and replaces weak entries.

### Final output

The result consumed by the service is the **reflection task's output** (`result.pydantic`), not the initial picking task. This ensures the refined version is always used.

---

## 6. Architecture: Data Flow After Changes

```
POST /recommendations/stocks
        │
        ▼
RecommendationsService.execute_stock_recommendations(market="ALL")
        │
        ├─── asyncio.gather ─────────────────────────┐
        │                                             │
        ▼                                             ▼
_run_market_analysis("US")             _run_market_analysis("IN")
        │                                             │
  Sector crew (sequential)               Sector crew (sequential)
  SectorRankingOutput                    SectorRankingOutput
        │                                             │
  asyncio.gather                          asyncio.gather
  ┌─────┬─────┬─────┐                ┌─────┬─────┬─────┐
  │     │     │     │                │     │     │     │
  ▼     ▼     ▼     │                ▼     ▼     ▼     │
Tech  Finance Energy │              IT  Banking Energy  │
crew  crew    crew   │              crew  crew   crew   │
  │     │     │     │                │     │     │     │
  └─────┴─────┴─────┘                └─────┴─────┴─────┘
        │                                             │
Each crew (Process.hierarchical):                     │
  manager_agent = Investment Advisor                  │
  workers = [Data Analyst]                            │
  tasks = [find_top_stocks, reflect_on_stock_picks]   │
        │                                             │
        └───────────── combined results ──────────────┘
                              │
                    Final response dict
```

---

## 7. File Change Summary

| File | Action | What changes |
|---|---|---|
| `app/services/recommendations_service.py` | Modify | Parallel gather for sector crews and market loops; `_run_stock_crew_for_sector` and `_run_fund_crew_for_sector` helper methods; hierarchical crew config; timeout 60→90 |
| `app/crew/tasks.py` | Modify | Add `reflect_on_stock_picks` and `reflect_on_fund_picks` tasks with `context` chaining and `output_pydantic` |
| `tests/test_recommendations_service.py` | Modify | Update to verify parallel execution, partial failure handling, and reflection task inclusion |

No changes to: `agents.py`, `output_models.py`, `chat_service.py`, `crew_service.py`, API routers, or response models.

---

## 8. Testing Strategy

### Unit tests (updated: `test_recommendations_service.py`)

| Test | Verifies |
|---|---|
| `test_stock_sectors_run_in_parallel` | `asyncio.gather` called with 3 coroutines for 3 sectors |
| `test_partial_sector_failure_excluded` | One sector raises exception; other 2 sectors still return results |
| `test_all_sectors_fail_raises_error` | All sectors fail → `CrewExecutionError` raised |
| `test_hierarchical_crew_uses_manager_agent` | `Crew` instantiated with `process=Process.hierarchical` and `manager_agent` set |
| `test_reflection_task_in_crew_tasks` | Both `find_top_stocks` and `reflect_on_stock_picks` present in crew task list |
| `test_us_and_in_sector_crews_run_in_parallel` | For `market="ALL"`, both market analyses fire concurrently |

### Integration tests (existing: `test_stocks.py`, `test_funds.py`)

No changes to test files — existing assertions (real symbol strings, populated metrics) remain valid and still pass. The API response shape is unchanged.

---

## 9. Out of Scope

- Chat service changes (no parallelism or reflection needed — single stock, single query)
- Frontend changes
- CrewAI memory persistence across HTTP requests (would require a vector store integration)
- Dynamic sector discovery (still uses static sector lists from `SectorStocksMapperTool`)
- India mutual fund support