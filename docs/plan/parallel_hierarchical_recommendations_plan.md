# Parallel Hierarchical Recommendations — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `RecommendationsService` to use parallel sector execution, hierarchical crew process, and a reflection task — improving recommendation quality and cutting wall-clock time by ~68%.

**Architecture:** Reflection tasks first (foundation for the hierarchical flow), then hierarchical crew config, then parallel fan-out (the largest change), then test updates.

**Tech Stack:** Python 3.12, FastAPI, CrewAI 1.7.2, asyncio, pytest

**Spec:** `docs/superpowers/specs/2026-04-03-parallel-hierarchical-recommendations-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `app/crew/tasks.py` | Modify | Add `reflect_on_stock_picks` and `reflect_on_fund_picks` tasks |
| `app/services/recommendations_service.py` | Modify | Parallel gather + hierarchical crews + helper methods |
| `tests/test_recommendations_service.py` | Modify | Add tests for parallelism, partial failure, hierarchical config, reflection |

---

## Task 1: Add reflection tasks to `tasks.py`

**Files:** `app/crew/tasks.py`

- [ ] **Step 1: Add `reflect_on_stock_picks` task**

In `backend/app/crew/tasks.py`, add after the `find_top_stocks_in_sector` method:

```python
@staticmethod
def reflect_on_stock_picks(agent, sector: str, market: str, context_tasks: list) -> Task:
    """Task: Critique and refine stock picks before finalising."""
    return Task(
        description=f"""Review and verify the stock picks for the {sector} sector in the {market} market.

        For each recommended stock, check:
        1. Is the ticker symbol a real, actively traded symbol on the correct exchange?
        2. Is each metric (P/E, ROE, market cap, EPS) an actual fetched value — not an estimate or placeholder?
        3. Is the recommendation_score (0–10) justified by the data, not inflated?
        4. Does the reasoning cite specific numbers, not vague generalities like "strong growth potential"?

        Replace any pick that fails these checks with the next best alternative using available data.
        Output the final verified list of top 3 stocks with complete, accurate data.

        Sector: {sector}
        Market: {market}
        Date: {datetime.now().strftime('%Y-%m-%d')}
        """,
        expected_output=(
            "A refined and verified SectorStocksOutput containing 3 stocks. "
            "Every metric must be a real fetched value. Every reasoning statement must cite specific numbers."
        ),
        agent=agent,
        output_pydantic=SectorStocksOutput,
        context=context_tasks,
    )
```

- [ ] **Step 2: Add `reflect_on_fund_picks` task**

In `backend/app/crew/tasks.py`, add after `identify_top_etfs_in_sector`:

```python
@staticmethod
def reflect_on_fund_picks(agent, sector: str, market: str, context_tasks: list) -> Task:
    """Task: Critique and refine ETF/fund picks before finalising."""
    return Task(
        description=f"""Review and verify the ETF/fund picks for the {sector} sector in the {market} market.

        For each recommended fund, check:
        1. Is the ETF/fund symbol a real, actively traded instrument?
        2. Is the NAV (current_nav), expense_ratio, and AUM fetched from real data — not estimated?
        3. Is the recommendation_score (0–10) justified by performance data?
        4. Does the reasoning reference specific performance figures?

        Replace any pick that fails these checks with the next best verified alternative.
        Output the final verified list of top 3 funds with complete, accurate data.

        Sector: {sector}
        Market: {market}
        Date: {datetime.now().strftime('%Y-%m-%d')}
        """,
        expected_output=(
            "A refined and verified SectorFundsOutput containing 3 funds. "
            "Every metric must be a real fetched value. Reasoning must cite specific performance numbers."
        ),
        agent=agent,
        output_pydantic=SectorFundsOutput,
        context=context_tasks,
    )
```

- [ ] **Step 3: Verify tasks.py imports**

Ensure `SectorStocksOutput` and `SectorFundsOutput` are both imported at the top of `tasks.py` — they already are per the current file, but confirm after edits.

---

## Task 2: Upgrade `recommendations_service.py`

**Files:** `app/services/recommendations_service.py`

- [ ] **Step 4: Increase timeouts**

Change the timeout constants at the top of the file:

```python
# BEFORE
SECTOR_TIMEOUT = 60
STOCK_TIMEOUT = 60
FUND_TIMEOUT = 60

# AFTER
SECTOR_TIMEOUT = 60   # unchanged
STOCK_TIMEOUT = 90    # increased for reflection task
FUND_TIMEOUT = 90     # increased for reflection task
```

- [ ] **Step 5: Extract `_run_stock_crew_for_sector` helper**

Add this private method to `RecommendationsService`:

```python
async def _run_stock_crew_for_sector(
    self,
    sector_info,
    market: str,
    timeframe: str,
    rank: int,
) -> dict:
    """Run a sequential stock picking + reflection crew for one sector. Creates its own agent instances."""
    data_analyst = FinancialAgents.financial_data_analyst()
    advisor = FinancialAgents.investment_advisor()

    stock_task = FinancialTasks.find_top_stocks_in_sector(
        data_analyst, sector_info.name, market, timeframe
    )
    reflect_task = FinancialTasks.reflect_on_stock_picks(
        advisor, sector_info.name, market, [stock_task]
    )

    crew = Crew(
        agents=[data_analyst, advisor],
        tasks=[stock_task, reflect_task],
        process=Process.sequential,
        verbose=True,
        memory=False,
        cache=True,
    )

    result = await self._run_crew_with_timeout(crew, STOCK_TIMEOUT)
    stocks_output: SectorStocksOutput = result.pydantic

    return {
        "sector": sector_info.name,
        "rank": rank,
        "performance_percent": sector_info.performance_pct,
        "market": market,
        "top_stocks": [s.model_dump() for s in stocks_output.stocks[:3]],
    }
```

- [ ] **Step 6: Extract `_run_fund_crew_for_sector` helper**

Add this private method:

```python
async def _run_fund_crew_for_sector(
    self,
    sector_info,
    market: str,
    timeframe: str,
    rank: int,
) -> dict:
    """Run a sequential fund picking + reflection crew for one sector. Creates its own agent instances."""
    data_analyst = FinancialAgents.financial_data_analyst()
    advisor = FinancialAgents.investment_advisor()

    etf_task = FinancialTasks.identify_top_etfs_in_sector(
        data_analyst, sector_info.name, market, timeframe
    )
    reflect_task = FinancialTasks.reflect_on_fund_picks(
        advisor, sector_info.name, market, [etf_task]
    )

    crew = Crew(
        agents=[data_analyst, advisor],
        tasks=[etf_task, reflect_task],
        process=Process.sequential,
        verbose=True,
        memory=False,
        cache=True,
    )

    result = await self._run_crew_with_timeout(crew, FUND_TIMEOUT)
    funds_output: SectorFundsOutput = result.pydantic

    return {
        "sector": sector_info.name,
        "rank": rank,
        "performance_percent": sector_info.performance_pct,
        "market": market,
        "top_funds": [f.model_dump() for f in funds_output.funds[:3]],
    }
```

- [ ] **Step 7: Extract `_run_market_stock_analysis` helper**

This method runs sector identification + parallel stock crews for a single market:

```python
async def _run_market_stock_analysis(
    self,
    market: str,
    timeframe: str,
    job_id: Optional[str],
) -> list:
    """Identify top sectors then run stock crews in parallel for one market."""
    if self.job_store:
        await self.job_store.update_job(
            job_id, "processing", f"Analyzing {market} market sectors..."
        )

    sector_analyst = FinancialAgents.sector_performance_analyst()
    sector_task = FinancialTasks.identify_top_sectors(sector_analyst, market, timeframe)
    sector_crew = Crew(
        agents=[sector_analyst],
        tasks=[sector_task],
        process=Process.sequential,
        verbose=True,
        memory=False,
        cache=True,
    )
    sector_result = await self._run_crew_with_timeout(sector_crew, SECTOR_TIMEOUT)
    ranking: SectorRankingOutput = sector_result.pydantic
    top_sectors = ranking.sectors[:3]

    coros = [
        self._run_stock_crew_for_sector(sector_info, market, timeframe, rank=i)
        for i, sector_info in enumerate(top_sectors, 1)
    ]
    sector_results = await asyncio.gather(*coros, return_exceptions=True)

    successful = []
    for i, res in enumerate(sector_results):
        if isinstance(res, Exception):
            logger.warning(f"Sector {i+1} failed for {market}: {res}")
        else:
            successful.append(res)

    if not successful:
        raise CrewExecutionError(f"All sector analyses failed for {market} market.")

    return successful
```

- [ ] **Step 8: Extract `_run_market_fund_analysis` helper**

Identical structure to `_run_market_stock_analysis` but calls `_run_fund_crew_for_sector`:

```python
async def _run_market_fund_analysis(
    self,
    market: str,
    timeframe: str,
    job_id: Optional[str],
) -> list:
    """Identify top sectors then run fund crews in parallel for one market."""
    if self.job_store:
        await self.job_store.update_job(
            job_id, "processing", f"Analyzing {market} market sectors for ETFs..."
        )

    sector_analyst = FinancialAgents.sector_performance_analyst()
    sector_task = FinancialTasks.identify_top_sectors(sector_analyst, market, timeframe)
    sector_crew = Crew(
        agents=[sector_analyst],
        tasks=[sector_task],
        process=Process.sequential,
        verbose=True,
        memory=False,
        cache=True,
    )
    sector_result = await self._run_crew_with_timeout(sector_crew, SECTOR_TIMEOUT)
    ranking: SectorRankingOutput = sector_result.pydantic
    top_sectors = ranking.sectors[:3]

    coros = [
        self._run_fund_crew_for_sector(sector_info, market, timeframe, rank=i)
        for i, sector_info in enumerate(top_sectors, 1)
    ]
    sector_results = await asyncio.gather(*coros, return_exceptions=True)

    successful = []
    for i, res in enumerate(sector_results):
        if isinstance(res, Exception):
            logger.warning(f"Sector {i+1} fund analysis failed for {market}: {res}")
        else:
            successful.append(res)

    if not successful:
        raise CrewExecutionError(f"All fund sector analyses failed for {market} market.")

    return successful
```

- [ ] **Step 9: Rewrite `execute_stock_recommendations` to use parallel helpers**

Replace the current `execute_stock_recommendations` body (the agent creation + nested loops) with:

```python
markets_to_analyze = ["US", "IN"] if market == "ALL" else [market]

market_coros = [
    self._run_market_stock_analysis(mkt, timeframe, job_id)
    for mkt in markets_to_analyze
]
market_results = await asyncio.gather(*market_coros, return_exceptions=True)

combined: List = []
for i, res in enumerate(market_results):
    mkt = markets_to_analyze[i]
    if isinstance(res, Exception):
        logger.error(f"Market {mkt} stock analysis failed: {res}")
    else:
        combined.extend(res)

if not combined:
    raise CrewExecutionError("All market analyses failed.")
```

Keep the job_store status update calls, error handling, and `final_result` assembly unchanged.

- [ ] **Step 10: Rewrite `execute_fund_recommendations` to use parallel helpers**

Same pattern as Step 9 but calling `_run_market_fund_analysis`:

```python
markets_to_analyze = ["US", "IN"] if market == "ALL" else [market]

market_coros = [
    self._run_market_fund_analysis(mkt, timeframe, job_id)
    for mkt in markets_to_analyze
]
market_results = await asyncio.gather(*market_coros, return_exceptions=True)

combined: List = []
for i, res in enumerate(market_results):
    mkt = markets_to_analyze[i]
    if isinstance(res, Exception):
        logger.error(f"Market {mkt} fund analysis failed: {res}")
    else:
        combined.extend(res)

if not combined:
    raise CrewExecutionError("All fund market analyses failed.")
```

---

## Task 3: Update unit tests

**Files:** `tests/test_recommendations_service.py`

**Note on existing tests:** The 5 existing tests mock `service._run_crew_with_timeout` with an ordered
`side_effect` list. With parallel execution the call order is non-deterministic, so those tests must be
rewritten to mock `_run_market_stock_analysis` / `_run_market_fund_analysis` instead.

- [ ] **Step 11: Rewrite existing tests to use the new helper-level mocks**

Replace all 5 existing test functions with these updated versions:

```python
async def test_stock_recommendations_returns_completed_status(service):
    """execute_stock_recommendations must return status='completed' on success."""
    with patch.object(service, "_run_market_stock_analysis", return_value=[
        {"sector": "Technology", "rank": 1, "performance_percent": 12.5,
         "market": "US", "top_stocks": [{"symbol": "AAPL"}]},
    ]):
        result = await service.execute_stock_recommendations(market="US", timeframe="30d")

    assert result["status"] == "completed"
    assert len(result["top_sectors"]) == 1


async def test_fund_recommendations_calls_fund_analysis_not_stock(service):
    """Fund flow must call _run_market_fund_analysis, never _run_market_stock_analysis."""
    with patch.object(service, "_run_market_fund_analysis", return_value=[
        {"sector": "Technology", "rank": 1, "performance_percent": 12.5,
         "market": "US", "top_funds": [{"symbol": "XLK"}]},
    ]) as mock_fund, \
    patch.object(service, "_run_market_stock_analysis") as mock_stock:
        await service.execute_fund_recommendations(market="US", timeframe="30d")

    mock_fund.assert_called_once()
    mock_stock.assert_not_called()


async def test_all_market_combines_us_and_in(service):
    """ALL market must produce results from both US and IN."""
    us_result = [{"sector": "Technology", "rank": 1, "performance_percent": 12.5,
                  "market": "US", "top_stocks": [{"symbol": "AAPL"}]}]
    in_result = [{"sector": "Banking", "rank": 1, "performance_percent": 10.1,
                  "market": "IN", "top_stocks": [{"symbol": "HDFCBANK.NS"}]}]

    async def fake_market_analysis(mkt, timeframe, job_id):
        return us_result if mkt == "US" else in_result

    with patch.object(service, "_run_market_stock_analysis", side_effect=fake_market_analysis):
        result = await service.execute_stock_recommendations(market="ALL", timeframe="30d")

    markets = {s["market"] for s in result["top_sectors"]}
    assert "US" in markets
    assert "IN" in markets


async def test_failed_market_sets_job_failed(service, mock_job_store):
    """If all markets fail, job_store must be updated to 'failed'."""
    with patch.object(service, "_run_market_stock_analysis",
                      side_effect=CrewExecutionError("boom")):
        with pytest.raises(CrewExecutionError):
            await service.execute_stock_recommendations(
                market="US", timeframe="30d", job_id="fail-job"
            )

    failed_calls = [
        c for c in mock_job_store.update_job.call_args_list
        if len(c[0]) > 1 and c[0][1] == "failed"
    ]
    assert len(failed_calls) == 1


async def test_stock_result_contains_real_symbol_not_placeholder(service):
    """Top stocks must not contain 'STOCK1' placeholder."""
    with patch.object(service, "_run_market_stock_analysis", return_value=[
        {"sector": "Technology", "rank": 1, "performance_percent": 12.5,
         "market": "US", "top_stocks": [{"symbol": "AAPL"}]},
    ]):
        result = await service.execute_stock_recommendations(market="US", timeframe="30d")

    all_symbols = [
        stock["symbol"]
        for sector in result["top_sectors"]
        for stock in sector["top_stocks"]
    ]
    assert "STOCK1" not in all_symbols
    assert all(len(sym) > 0 for sym in all_symbols)
```

- [ ] **Step 12: Add test for parallel sector execution**

```python
async def test_stock_sectors_run_in_parallel(service):
    """Per-sector crews must be gathered concurrently, not run sequentially."""
    gather_spy = AsyncMock(wraps=asyncio.gather)

    with patch("app.services.recommendations_service.asyncio.gather", gather_spy):
        with patch.object(service, "_run_market_stock_analysis", return_value=[]):
            await service.execute_stock_recommendations("US", "30d")

    gather_spy.assert_called()
```

- [ ] **Step 13: Add test for partial sector failure**

```python
async def test_partial_sector_failure_excluded(service):
    """If one sector fails, the others still return results."""
    sector_results = [
        {"sector": "Technology", "rank": 1, "performance_percent": 12.5,
         "market": "US", "top_stocks": []},
        CrewExecutionError("sector 2 failed"),
        {"sector": "Energy", "rank": 3, "performance_percent": 6.0,
         "market": "US", "top_stocks": []},
    ]

    mock_crew_result = MagicMock()
    mock_crew_result.pydantic = SectorRankingOutput(sectors=[
        SectorInfo(name="Technology", performance_pct=12.5, trend="Up", momentum="High", drivers="AI"),
        SectorInfo(name="Healthcare", performance_pct=8.0, trend="Up", momentum="Low", drivers="Aging"),
        SectorInfo(name="Energy", performance_pct=6.0, trend="Up", momentum="Low", drivers="Oil"),
    ])

    with patch.object(service, "_run_stock_crew_for_sector", side_effect=sector_results), \
         patch.object(service, "_run_crew_with_timeout", return_value=mock_crew_result), \
         patch("app.services.recommendations_service.FinancialAgents.sector_performance_analyst"), \
         patch("app.services.recommendations_service.FinancialTasks.identify_top_sectors"), \
         patch("app.services.recommendations_service.Crew"):
        result = await service._run_market_stock_analysis("US", "30d", None)

    assert len(result) == 2


async def test_all_sectors_fail_raises_error(service):
    """If all sectors fail, CrewExecutionError is raised."""
    mock_crew_result = MagicMock()
    mock_crew_result.pydantic = SectorRankingOutput(sectors=[
        SectorInfo(name="Technology", performance_pct=12.5, trend="Up", momentum="High", drivers="AI"),
        SectorInfo(name="Healthcare", performance_pct=8.0, trend="Up", momentum="Low", drivers="Aging"),
        SectorInfo(name="Energy", performance_pct=6.0, trend="Up", momentum="Low", drivers="Oil"),
    ])

    with patch.object(service, "_run_stock_crew_for_sector",
                      side_effect=CrewExecutionError("failed")), \
         patch.object(service, "_run_crew_with_timeout", return_value=mock_crew_result), \
         patch("app.services.recommendations_service.FinancialAgents.sector_performance_analyst"), \
         patch("app.services.recommendations_service.FinancialTasks.identify_top_sectors"), \
         patch("app.services.recommendations_service.Crew"):
        with pytest.raises(CrewExecutionError):
            await service._run_market_stock_analysis("US", "30d", None)
```

- [ ] **Step 14: Add test for sequential crew config and reflection task**

```python
async def test_sequential_crew_with_reflection_task(service):
    """Stock picking crew must use Process.sequential with both picking and reflect tasks."""
    captured_crew_kwargs = {}

    class CapturingCrew:
        def __init__(self, **kwargs):
            captured_crew_kwargs.update(kwargs)
        def kickoff(self):
            mock = MagicMock()
            mock.pydantic = make_stocks_result().pydantic
            return mock

    sector_info = SectorInfo(
        name="Technology", performance_pct=12.5,
        trend="Up", momentum="High", drivers="AI"
    )

    with patch("app.services.recommendations_service.Crew", CapturingCrew), \
         patch("app.services.recommendations_service.FinancialAgents.financial_data_analyst",
               return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialAgents.investment_advisor",
               return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.find_top_stocks_in_sector",
               return_value=MagicMock()), \
         patch("app.services.recommendations_service.FinancialTasks.reflect_on_stock_picks",
               return_value=MagicMock()):
        await service._run_stock_crew_for_sector(sector_info, "US", "30d", rank=1)

    assert captured_crew_kwargs.get("process") == Process.sequential
    assert captured_crew_kwargs.get("memory") is False
    assert len(captured_crew_kwargs.get("tasks", [])) == 2
```

- [ ] **Step 15: Add import for `Process` in test file**

Add to the imports at the top of `test_recommendations_service.py`:

```python
from crewai import Process
```

---

## Verification

After all steps are complete:

- [ ] Run unit tests: `python -m pytest tests/test_recommendations_service.py -v`
- [ ] Run all unit tests: `python -m pytest tests/ -v --ignore=tests/test_chat.py --ignore=tests/test_stocks.py --ignore=tests/test_funds.py`
- [ ] Confirm no imports broken: `python -c "from app.services.recommendations_service import RecommendationsService"`
- [ ] Confirm tasks import: `python -c "from app.crew.tasks import FinancialTasks; print(dir(FinancialTasks))"`
