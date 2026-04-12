# Gemma Model — Iterative Free-Tier Fixes Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Incrementally test three cheap fixes — model swap, iteration/timeout increase, and batch tool rewrite — to determine the minimum change that makes stock/fund recommendations reliable on free-tier models, before committing to the full architectural redesign in `docs/superpowers/specs/2026-04-11-free-model-architecture-design.md`.

**Architecture:** Three self-contained layers, each additive on top of the last. Each layer has a defined pass/fail criterion checked in live logs before proceeding. No layer touches the architectural pre-fetch approach — that remains a separate decision.

**Tech Stack:** Python 3.12, CrewAI 1.7.2, yfinance, FastAPI, OpenRouter (model: `google/gemma-3-27b-it:free`)

---

## Baseline: How to Observe Failure

Before any changes, know what failure looks like so each layer's result can be compared.

**Failure signature in logs:**
```
WARNING  Sector N stock analysis failed for IN: 3 validation errors for SectorStocksOutput
         sector / market / stocks  Field required
         input_value={'thought': '...', 'action': '...'}
```

**What this means:** `max_iter` was hit before the JSON synthesis step. The last agent output was a ReAct `{thought, action}` dict, not `SectorStocksOutput`.

**Success signature:**
```
INFO     Stock recommendations completed: <job_id>
```
No `ValidationError` warnings for any sector.

---

## Files Touched Across All Layers

| File | Layer | Change |
|---|---|---|
| `backend/.env` | 1 | `LLM_MODEL_NAME` value |
| `backend/.env.example` | 1 | document new model |
| `backend/app/crew/agents.py` | 2 | `max_iter` on `financial_data_analyst` and `investment_advisor` |
| `backend/app/config.py` | 2 | `CREW_TIMEOUT_SECONDS` default |
| `backend/.env.example` | 2 | document new timeout |
| `backend/app/crew/tools/financial_data.py` | 3 | rewrite `PortfolioDataTool._run` |
| `backend/app/crew/tasks.py` | 3 | update `find_top_stocks_in_sector` description |
| `backend/tests/test_crew_service.py` | 2 | assert new `max_iter` values |
| `backend/tests/test_recommendations_service.py` | 3 | `PortfolioDataTool` output format |

---

## Layer 1 — Model Swap Only

**Hypothesis:** `google/gemma-3-27b-it:free` follows JSON schema more reliably than `meta-llama/llama-4-scout:free`, reducing (but not eliminating) ValidationErrors.

**No code changes.** Config only.

**Pass criterion:** At least 1 out of 3 sectors completes successfully per market (previously 0/3).  
**Fail criterion:** All 3 sectors still fail with the same ValidationError signature.

---

### Task 1: Switch model in .env

**Files:**
- Modify: `backend/.env` (not tracked by git — edit manually)
- Modify: `backend/.env.example`

- [ ] **Step 1: Update .env**

  Open `backend/.env` and change:
  ```
  LLM_MODEL_NAME=meta-llama/llama-4-scout:free
  ```
  to:
  ```
  LLM_MODEL_NAME=google/gemma-3-27b-it:free
  ```

- [ ] **Step 2: Update .env.example**

  In `backend/.env.example`, change the `LLM_MODEL_NAME` line to:
  ```
  LLM_MODEL_NAME=google/gemma-3-27b-it:free
  ```

- [ ] **Step 3: Restart the API container**

  ```bash
  docker compose restart stocks_analyzer_api
  ```
  Or if running locally:
  ```bash
  # Kill uvicorn, then:
  cd backend
  source .venv/Scripts/activate
  uvicorn app.main:app --reload
  ```

- [ ] **Step 4: Trigger a stock recommendation and observe logs**

  ```bash
  curl -X POST http://localhost:8000/api/v1/stocks/recommendations \
    -H "Content-Type: application/json" \
    -d '{"market": "IN", "timeframe": "30d"}'
  ```

  Watch container logs. Wait up to 90 seconds for the background job to complete.

  **Record result** (one of):
  - `INFO  Stock recommendations completed` — Layer 1 passed
  - Still `ValidationError for SectorStocksOutput` on all 3 sectors — Layer 1 failed, proceed to Layer 2 anyway
  - 1–2 sectors succeed, 1–2 fail — partial improvement, proceed to Layer 2

- [ ] **Step 5: Run unit tests to confirm nothing broke**

  ```bash
  cd backend
  python -m pytest tests/test_job_store.py tests/test_output_models.py tests/test_crew_service.py tests/test_chat_service.py tests/test_recommendations_service.py -v
  ```

  Expected: all 44 existing tests pass (model name is not asserted anywhere in unit tests).

- [ ] **Step 6: Commit**

  ```bash
  git add backend/.env.example
  git commit -m "config: switch to gemma-3-27b-it:free for free-tier reliability testing"
  ```

  Note: `.env` is gitignored — do not add it.

---

## Layer 2 — Increase max_iter and CREW_TIMEOUT_SECONDS

**Hypothesis:** With `max_iter=8` the agent has enough room to finish 1 list call + 5 data calls + 1 JSON synthesis = 7 steps. With `max_iter=5` step 6 is never reached.

**Additive on top of Layer 1** (Gemma model still active).

**Pass criterion:** All 3 sectors complete for at least one market (IN or US) in a single run, no ValidationErrors.  
**Fail criterion:** Still hitting `max_iter` (log shows `thought/action` as final answer).

---

### Task 2: Increase max_iter on financial_data_analyst and investment_advisor

**Files:**
- Modify: `backend/app/crew/agents.py:126` (`financial_data_analyst`)
- Modify: `backend/app/crew/agents.py:216` (`investment_advisor`)

- [ ] **Step 1: Write failing tests first**

  In `backend/tests/test_crew_service.py`, add at the end of the file:

  ```python
  def test_financial_data_analyst_max_iter():
      """financial_data_analyst must have max_iter >= 8 to handle 1 list + 5 data + 1 JSON steps."""
      with patch("app.crew.agents.get_llm", return_value=MagicMock()):
          agent = FinancialAgents.financial_data_analyst()
      assert agent.max_iter >= 8


  def test_investment_advisor_max_iter():
      """investment_advisor must have max_iter >= 5 for reflect task (context read + verify + JSON)."""
      with patch("app.crew.agents.get_llm", return_value=MagicMock()):
          agent = FinancialAgents.investment_advisor()
      assert agent.max_iter >= 5
  ```

- [ ] **Step 2: Run tests to confirm they fail**

  ```bash
  cd backend
  python -m pytest tests/test_crew_service.py::test_financial_data_analyst_max_iter tests/test_crew_service.py::test_investment_advisor_max_iter -v
  ```

  Expected:
  ```
  FAILED tests/test_crew_service.py::test_financial_data_analyst_max_iter
         AssertionError: assert 5 >= 8
  FAILED tests/test_crew_service.py::test_investment_advisor_max_iter
         AssertionError: assert 3 >= 5
  ```

- [ ] **Step 3: Update max_iter in agents.py**

  In `backend/app/crew/agents.py`, in `financial_data_analyst`:
  ```python
  # Change:
  max_iter=5,
  # To:
  max_iter=8,
  ```

  In `investment_advisor`:
  ```python
  # Change:
  max_iter=3,
  # To:
  max_iter=5,
  ```

- [ ] **Step 4: Run tests to confirm they pass**

  ```bash
  python -m pytest tests/test_crew_service.py::test_financial_data_analyst_max_iter tests/test_crew_service.py::test_investment_advisor_max_iter -v
  ```

  Expected: both PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add backend/app/crew/agents.py backend/tests/test_crew_service.py
  git commit -m "feat: increase max_iter (analyst: 5→8, advisor: 3→5) for free-tier iteration budget"
  ```

---

### Task 3: Increase CREW_TIMEOUT_SECONDS

**Files:**
- Modify: `backend/app/config.py:47`
- Modify: `backend/.env.example`

- [ ] **Step 1: Write failing test**

  In `backend/tests/test_crew_service.py`, add:

  ```python
  def test_crew_timeout_is_sufficient_for_high_max_iter():
      """Timeout must be at least 180s — with max_iter=8 each iteration can take ~15s on free tier."""
      from app.config import settings
      assert settings.CREW_TIMEOUT_SECONDS >= 180
  ```

- [ ] **Step 2: Run test to confirm it fails**

  ```bash
  python -m pytest tests/test_crew_service.py::test_crew_timeout_is_sufficient_for_high_max_iter -v
  ```

  Expected:
  ```
  FAILED  AssertionError: assert 90 >= 180
  ```

- [ ] **Step 3: Update default in config.py**

  In `backend/app/config.py`, change:
  ```python
  CREW_TIMEOUT_SECONDS: int = 90
  ```
  to:
  ```python
  CREW_TIMEOUT_SECONDS: int = 180
  ```

- [ ] **Step 4: Update .env.example**

  In `backend/.env.example`, update the crew timeout line to:
  ```
  CREW_TIMEOUT_SECONDS=180
  ```

- [ ] **Step 5: Run test to confirm it passes**

  ```bash
  python -m pytest tests/test_crew_service.py::test_crew_timeout_is_sufficient_for_high_max_iter -v
  ```

  Expected: PASS.

- [ ] **Step 6: Run full unit test suite**

  ```bash
  python -m pytest tests/test_job_store.py tests/test_output_models.py tests/test_crew_service.py tests/test_chat_service.py tests/test_recommendations_service.py -v
  ```

  Expected: all tests pass.

- [ ] **Step 7: Commit**

  ```bash
  git add backend/app/config.py backend/.env.example
  git commit -m "config: increase CREW_TIMEOUT_SECONDS 90→180 to match max_iter=8 budget"
  ```

---

### Task 4: Observe Layer 2 results

- [ ] **Step 1: Restart API and trigger a test request**

  ```bash
  docker compose restart stocks_analyzer_api
  # or restart uvicorn locally

  curl -X POST http://localhost:8000/api/v1/stocks/recommendations \
    -H "Content-Type: application/json" \
    -d '{"market": "IN", "timeframe": "30d"}'
  ```

  Watch logs for up to 3 minutes (180s timeout × 3 sectors).

  **Record result:**
  - All 3 sectors complete — Layer 2 passed, iteration budget was the issue
  - 2/3 sectors complete — partial improvement, proceed to Layer 3
  - Still 0/3 with same `thought/action` ValidationError — max_iter is still not enough, proceed to Layer 3
  - 0/3 but error changes to timeout — the model is running iterations but not outputting JSON. Still proceed to Layer 3.

---

## Layer 3 — Batch Tool: Rewrite PortfolioDataTool

**Hypothesis:** The agent is calling `YFinanceDataTool` once per stock (5 iterations for 5 stocks). If it calls `PortfolioDataTool` once with all 5 symbols, it uses only 1 iteration for data fetching, leaving room for JSON output within `max_iter=8`.

**Key change:** `PortfolioDataTool._run` currently returns `str(DataFrame)` — raw tabular data that is useless to an LLM. Rewrite it to return a clean, per-stock summary. Update the task description to explicitly instruct the agent to use this tool for batch fetching.

**Additive on top of Layers 1 + 2** (Gemma model, max_iter=8, timeout=180 still active).

**Pass criterion:** Agent calls `PortfolioDataTool` once (visible in verbose logs) and then outputs valid JSON. No `YFinanceDataTool` calls per-stock.  
**Fail criterion:** Agent still calls `YFinanceDataTool` per-stock, or `PortfolioDataTool` output is misread and agent retries.

---

### Task 5: Rewrite PortfolioDataTool._run

**Files:**
- Modify: `backend/app/crew/tools/financial_data.py:19-30`
- Test: `backend/tests/test_crew_service.py`

- [ ] **Step 1: Write failing test**

  In `backend/tests/test_crew_service.py`, add:

  ```python
  def test_portfolio_data_tool_returns_per_stock_summary():
      """PortfolioDataTool must return a readable per-stock text summary, not a raw DataFrame."""
      from app.crew.tools.financial_data import PortfolioDataTool
      from unittest.mock import patch, MagicMock
      import pandas as pd

      mock_hist = pd.DataFrame({"Close": [100.0, 102.0, 105.0]})

      mock_ticker = MagicMock()
      mock_ticker.info = {
          "longName": "Apple Inc.",
          "currentPrice": 175.5,
          "trailingPE": 28.5,
          "trailingEps": 6.13,
          "returnOnEquity": 0.35,
          "marketCap": 2_800_000_000_000,
          "debtToEquity": 1.8,
      }
      mock_ticker.history.return_value = mock_hist

      with patch("app.crew.tools.financial_data.yf.Ticker", return_value=mock_ticker), \
           patch("app.crew.tools.financial_data.yf.download",
                 return_value=pd.DataFrame({"Close": {"AAPL": pd.Series([100.0, 175.5])}})):
          tool = PortfolioDataTool()
          result = tool._run(symbols=["AAPL"], timeframe="30d")

      # Must contain structured fields — not a raw DataFrame dump
      assert "AAPL" in result
      assert "Apple Inc." in result
      assert "175.5" in result or "175" in result
      assert "P/E" in result or "pe_ratio" in result.lower() or "28.5" in result
      # Must NOT contain raw pandas index/column headers
      assert "Datetime" not in result
      assert "dtype:" not in result


  def test_portfolio_data_tool_handles_missing_symbol_gracefully():
      """PortfolioDataTool must skip symbols that yfinance can't fetch, not raise."""
      from app.crew.tools.financial_data import PortfolioDataTool
      from unittest.mock import patch, MagicMock
      import pandas as pd

      def raise_for_bad(symbol):
          if symbol == "BADSYM":
              raise Exception("not found")
          m = MagicMock()
          m.info = {"longName": "Good Corp", "currentPrice": 50.0,
                    "trailingPE": 10.0, "trailingEps": 5.0,
                    "returnOnEquity": 0.2, "marketCap": 1_000_000_000,
                    "debtToEquity": 0.5}
          m.history.return_value = pd.DataFrame({"Close": [48.0, 50.0]})
          return m

      with patch("app.crew.tools.financial_data.yf.Ticker", side_effect=raise_for_bad), \
           patch("app.crew.tools.financial_data.yf.download", return_value=pd.DataFrame()):
          tool = PortfolioDataTool()
          result = tool._run(symbols=["GOODSYM", "BADSYM"], timeframe="30d")

      assert "GOODSYM" in result
      assert "BADSYM" not in result   # silently skipped
  ```

- [ ] **Step 2: Run tests to confirm they fail**

  ```bash
  python -m pytest tests/test_crew_service.py::test_portfolio_data_tool_returns_per_stock_summary tests/test_crew_service.py::test_portfolio_data_tool_handles_missing_symbol_gracefully -v
  ```

  Expected: both FAIL (current output contains `dtype:` from raw DataFrame).

- [ ] **Step 3: Rewrite PortfolioDataTool._run**

  In `backend/app/crew/tools/financial_data.py`, replace the entire `PortfolioDataTool` class body (lines 13–30):

  ```python
  class PortfolioDataTool(BaseTool):
      name: str = "Multi-Stock Data Fetcher"
      description: str = """Fetch and compare financial data for multiple stocks in one call.
      Pass all symbols at once to get a structured per-stock summary with price, change %,
      P/E, EPS, ROE, market cap, and debt/equity. Far more efficient than fetching one stock
      at a time. Use this before ranking stocks within a sector."""
      args_schema: Type[BaseModel] = PortfolioDataInput

      def _run(self, symbols: list[str], timeframe: str = "30d") -> str:
          """Fetch metrics for all symbols and return a clean per-stock summary."""
          period_map = {"7d": "7d", "30d": "1mo", "90d": "3mo"}
          period = period_map.get(timeframe, "1mo")

          # Batch download closing prices for % change calculation
          try:
              hist_data = yf.download(
                  symbols, period=period, auto_adjust=True,
                  progress=False, threads=True
              )
          except Exception:
              hist_data = None

          results = []
          for symbol in symbols:
              try:
                  ticker = yf.Ticker(symbol)
                  info = ticker.info

                  # % change from batch history, fall back to 0 if unavailable
                  change_pct = 0.0
                  if hist_data is not None and not hist_data.empty:
                      try:
                          if len(symbols) == 1:
                              col = hist_data["Close"]
                          else:
                              col = hist_data["Close"][symbol]
                          col = col.dropna()
                          if len(col) >= 2:
                              change_pct = ((col.iloc[-1] - col.iloc[0]) / col.iloc[0]) * 100
                      except (KeyError, TypeError):
                          pass

                  roe_raw = info.get("returnOnEquity")
                  roe = round(roe_raw * 100, 1) if roe_raw else "N/A"
                  currency = "INR" if (".NS" in symbol or ".BO" in symbol) else "USD"

                  results.append({
                      "symbol": symbol,
                      "name": info.get("longName", info.get("shortName", symbol)),
                      "price": info.get("currentPrice", "N/A"),
                      "currency": currency,
                      "change_pct": round(change_pct, 2),
                      "pe_ratio": info.get("trailingPE", "N/A"),
                      "eps": info.get("trailingEps", "N/A"),
                      "roe": roe,
                      "market_cap": info.get("marketCap", "N/A"),
                      "debt_to_equity": info.get("debtToEquity", "N/A"),
                  })
              except Exception as e:
                  from app.utils.logger import get_logger
                  get_logger(__name__).warning(f"PortfolioDataTool: skipping {symbol}: {e}")
                  continue

          if not results:
              return f"Could not fetch data for any of: {', '.join(symbols)}"

          lines = [f"Stock Comparison ({timeframe}):", "=" * 60]
          for r in results:
              lines.append(
                  f"\n{r['symbol']} — {r['name']}\n"
                  f"  Price: {r['price']} {r['currency']},  Change({timeframe}): {r['change_pct']:+.1f}%\n"
                  f"  P/E: {r['pe_ratio']},  EPS: {r['eps']},  ROE: {r['roe']}%\n"
                  f"  Market Cap: {r['market_cap']},  Debt/Equity: {r['debt_to_equity']}"
              )
          return "\n".join(lines)
  ```

- [ ] **Step 4: Run tests to confirm they pass**

  ```bash
  python -m pytest tests/test_crew_service.py::test_portfolio_data_tool_returns_per_stock_summary tests/test_crew_service.py::test_portfolio_data_tool_handles_missing_symbol_gracefully -v
  ```

  Expected: both PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add backend/app/crew/tools/financial_data.py backend/tests/test_crew_service.py
  git commit -m "feat: rewrite PortfolioDataTool to return structured per-stock summary instead of raw DataFrame"
  ```

---

### Task 6: Update find_top_stocks_in_sector task description to guide batch tool use

**Files:**
- Modify: `backend/app/crew/tasks.py` — `find_top_stocks_in_sector` description only

The agent won't use `PortfolioDataTool` for batch fetching unless the task explicitly tells it to. The current description says "fetch financial data and performance for each stock" — that reads as "fetch one at a time." We need to guide it to call `PortfolioDataTool` with all symbols in a single call.

- [ ] **Step 1: Write failing test**

  In `backend/tests/test_crew_service.py`, add:

  ```python
  def test_find_top_stocks_task_description_guides_batch_fetch():
      """Task description must instruct agent to use batch tool, not per-stock fetching."""
      from app.crew.tasks import FinancialTasks
      task = FinancialTasks.find_top_stocks_in_sector(
          agent=MagicMock(), sector="Technology", market="US", timeframe="30d"
      )
      desc = task.description.lower()
      # Must mention the batch tool by name so the agent picks it up
      assert "multi-stock" in desc or "portfolio" in desc or "all symbols" in desc or "batch" in desc
      # Must NOT encourage per-stock iteration pattern
      assert "for each stock" not in desc
  ```

- [ ] **Step 2: Run test to confirm it fails**

  ```bash
  python -m pytest tests/test_crew_service.py::test_find_top_stocks_task_description_guides_batch_fetch -v
  ```

  Expected: FAIL (current description says "Fetch financial data and performance for each stock").

- [ ] **Step 3: Update find_top_stocks_in_sector description in tasks.py**

  In `backend/app/crew/tasks.py`, replace the `description` of `find_top_stocks_in_sector`:

  ```python
  description=f"""Find the top 3 stock picks in the {sector} sector for the {market} market.

  Your objectives — follow these steps IN ORDER:

  Step 1: Call the "Sector Stocks Finder" tool with sector="{sector}" and market="{market}"
          to get the list of stock symbols. Do NOT skip this step.

  Step 2: Take ALL the symbols returned and call "Multi-Stock Data Fetcher" ONCE with
          all symbols together. This is a single tool call — do NOT call "Stock Data Fetcher"
          separately for each symbol. Calling one tool with all symbols is more efficient.

  Step 3: Using ONLY the data returned by step 2, rank the top 3 stocks by:
          - Recent performance (change_pct over {timeframe})
          - Financial health (P/E ratio, ROE, debt/equity)
          - Market cap (stability proxy)
          Then output the final JSON.

  Sector: {sector}
  Market: {market}
  Timeframe: {timeframe}

  CRITICAL: Your FINAL answer must be ONLY a valid JSON object. Do NOT include any
  "thought", "action", "observation", or other ReAct-format fields in your final answer.
  Output pure JSON only — no preamble, no trailing text.
  """,
  ```

- [ ] **Step 4: Run test to confirm it passes**

  ```bash
  python -m pytest tests/test_crew_service.py::test_find_top_stocks_task_description_guides_batch_fetch -v
  ```

  Expected: PASS.

- [ ] **Step 5: Run full unit test suite**

  ```bash
  python -m pytest tests/test_job_store.py tests/test_output_models.py tests/test_crew_service.py tests/test_chat_service.py tests/test_recommendations_service.py -v
  ```

  Expected: all tests pass.

- [ ] **Step 6: Commit**

  ```bash
  git add backend/app/crew/tasks.py backend/tests/test_crew_service.py
  git commit -m "feat: guide agent to use batch PortfolioDataTool instead of per-stock YFinanceDataTool calls"
  ```

---

### Task 7: Observe Layer 3 results and record findings

- [ ] **Step 1: Restart and test**

  ```bash
  docker compose restart stocks_analyzer_api

  curl -X POST http://localhost:8000/api/v1/stocks/recommendations \
    -H "Content-Type: application/json" \
    -d '{"market": "IN", "timeframe": "30d"}'
  ```

  Wait up to 3 minutes. Inspect logs.

- [ ] **Step 2: Check verbose agent output**

  Look for this pattern in logs (success):
  ```
  Action: Multi-Stock Data Fetcher
  Action Input: {"symbols": ["TCS.NS", "INFY.NS", ...], "timeframe": "30d"}
  ...
  Final Answer: {"sector": "Technology", "market": "IN", "stocks": [...]}
  ```

  Look for this pattern (still failing):
  ```
  Action: Stock Data Fetcher
  Action Input: {"symbol": "TCS.NS", ...}   ← per-stock calls still happening
  ```

- [ ] **Step 3: Record findings in a comment block at the bottom of this plan**

  Update this file with:
  ```
  ## Results

  | Layer | Date | IN market | US market | Observations |
  |---|---|---|---|---|
  | 1 — Gemma model | YYYY-MM-DD | X/3 sectors | X/3 sectors | ... |
  | 2 — max_iter + timeout | YYYY-MM-DD | X/3 sectors | X/3 sectors | ... |
  | 3 — Batch tool | YYYY-MM-DD | X/3 sectors | X/3 sectors | ... |
  ```

---

## Decision Gate: After Layer 3

Based on results, choose one of:

**A — Layers fixed it (≥ 2/3 sectors reliably succeed):**
Keep all three changes. Optionally increase `max_iter` further or tune the batch tool. The full architectural redesign in `specs/2026-04-11-free-model-architecture-design.md` is deferred until the current approach proves insufficient again.

**B — Layers partially helped but inconsistent (1/3 or flaky):**
The free model is fundamentally unreliable for tool-call + JSON tasks. Proceed with the full pre-fetch architecture from the spec. The three layers are still worth keeping (they improve the path), but the pre-fetch redesign is now unblocked.

**C — No improvement after all three layers:**
The model is incapable of following the required pattern regardless of iteration budget. Proceed with the full pre-fetch architecture. Consider switching to a paid model (gpt-4o-mini) as an alternative path.

---

## Results

*(Fill in after running each layer)*

| Layer | Date | IN market | US market | Observations |
|---|---|---|---|---|
| 1 — Gemma model swap | — | — | — | — |
| 2 — max_iter=8, timeout=180 | — | — | — | — |
| 3 — Batch PortfolioDataTool | — | — | — | — |
