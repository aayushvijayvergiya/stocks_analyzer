# Pre-Fetch Architecture Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace tool-calling crew flows with a pre-fetch architecture where Python fetches all deterministic data and LLM agents only reason over prefetched context. Also fix the ghost-thread bug where crew threads keep running after API timeout.

**Architecture:** All yfinance/news/sector data is fetched in Python _before_ the crew runs. The crew kickoff is executed inside a **subprocess** that can be hard-terminated on timeout (solving Bug 3). Agents have NO tools and `max_iter=2`; their only job is to take prefetched JSON data in the task description and output a final Pydantic JSON. Reflection tasks are deleted (free-tier models cannot reliably produce ReAct format for them). Sectors remain serial per market; markets remain parallel via `asyncio.gather`.

**Tech Stack:** Python 3.12, FastAPI, CrewAI 1.7.2, yfinance, OpenRouter free-tier LLMs (`meta-llama/llama-4-scout:free`), Redis, pytest.

**Background — three bugs this plan fixes:**

1. **Bug 1 — ReAct format failures (Pydantic ValidationError):** Free-tier llama-4-scout returns `Final Answer: {"Action": "...", "Action Input": {...}}` as its structured output instead of real JSON, causing `SectorStocksOutput` validation to fail. Logs 2026-04-11 at 15:55:17 (Metal sector), 15:57:xx (Realty sector).
2. **Bug 2 — OpenRouter null-response crashes:** Free tier rate limiting causes `'NoneType' object is not subscriptable` inside the LLM wrapper. Logs at 15:58:18 and 16:00:32.
3. **Bug 3 — Ghost threads after timeout:** `loop.run_in_executor(None, crew.kickoff)` wrapped in `asyncio.wait_for` raises `TimeoutError` in the API layer but the underlying OS thread **cannot be cancelled** and keeps making LLM calls. Logs show Realty crew running 96 seconds after job was marked failed (15:59:41 → 16:01:17).

**Root cause for Bugs 1–2:** The current architecture lets free-tier LLMs drive tool calls via ReAct. They are not reliable at this. Fix: remove tools from agents and pre-fetch all data deterministically in Python.

**Root cause for Bug 3:** Python threads running sync C-extension code (yfinance, requests) cannot be interrupted. Fix: execute the crew in a child **process** spawned with `multiprocessing.get_context("spawn")` so we can call `proc.terminate()` / `proc.kill()` on timeout.

---

## File Structure

**New files:**
- `backend/app/services/crew_runner.py` — Subprocess-based cancellable crew runner. Contains `run_stock_crew_subprocess`, `run_fund_crew_subprocess`, `run_chat_crew_subprocess` (picklable module-level entry points) and the async `run_with_cancellation` wrapper.
- `backend/app/services/data_fetchers.py` — Deterministic Python data fetchers: `fetch_sector_stocks_sync`, `fetch_sector_etfs_sync`, `fetch_stock_snapshot_sync`, `fetch_stock_news_sync`.
- `backend/tests/test_crew_runner.py` — Unit tests for the subprocess runner.
- `backend/tests/test_data_fetchers.py` — Unit tests for the fetchers.

**Modified files:**
- `backend/app/crew/tasks.py` — New task signatures take `prefetched_*` data. Delete `reflect_on_stock_picks` and `reflect_on_fund_picks`. Rewrite `synthesize_chat_response`, `find_top_stocks_in_sector`, `identify_top_etfs_in_sector`.
- `backend/app/crew/agents.py` — Strip tools from `financial_data_analyst` and `investment_advisor`. Set `max_iter=2`. Update goals.
- `backend/app/services/recommendations_service.py` — Rewrite `_run_stock_crew_for_sector` / `_run_fund_crew_for_sector` to prefetch then call `run_with_cancellation`. Delete `_run_crew_with_timeout`.
- `backend/app/services/chat_service.py` — Prefetch metrics/news then call the cancellable runner. Delete `_run_crew_with_timeout`.
- `backend/app/config.py` — Lower `CREW_TIMEOUT_SECONDS` from 240 → 90.
- `backend/tests/test_recommendations_service.py` — Update reflection-task assertions; add pre-fetch path tests.
- `backend/tests/test_crew_service.py` — Relax `max_iter` assertions (>= 2), drop tools checks.

---

## Phase 0 — Environment Check

### Task 0.1: Verify working tree is clean before starting

- [ ] **Step 1: Check git status**

Run: `git status`
Expected: shows `feature/nextjs-frontend` branch with the existing modified files. If there is unrelated in-progress work, stash it before proceeding:

```bash
git stash push -m "pre-refactor-stash"
```

- [ ] **Step 2: Activate venv and confirm tests currently pass (baseline)**

Run:
```bash
cd backend
source .venv/Scripts/activate
python -m pytest tests/test_job_store.py tests/test_output_models.py tests/test_chat_service.py -v
```
Expected: all pass. These are tests that do NOT depend on the refactor. If any fail, stop and investigate first.

- [ ] **Step 3: Confirm Python multiprocessing spawn works on this Windows machine**

Run:
```bash
python -c "import multiprocessing as mp; ctx = mp.get_context('spawn'); print('spawn ok:', ctx)"
```
Expected: prints `spawn ok: <SpawnContext ...>`. If it errors, stop — this platform cannot support Phase 1.

---

## Phase 1 — Cancellable Crew Runner (fixes Bug 3)

**Why first:** Everything else depends on having a working cancellation mechanism. We build and test it in isolation before rewiring services.

### Task 1.1: Create `crew_runner.py` skeleton with `run_with_cancellation`

**Files:**
- Create: `backend/app/services/crew_runner.py`

- [ ] **Step 1: Write the file**

```python
"""
Cancellable crew runner using subprocess execution.

Problem: CrewAI's crew.kickoff() is sync and runs LLM calls via requests/yfinance,
which are C-extension blocking calls that cannot be interrupted from another
Python thread. When asyncio.wait_for fires on loop.run_in_executor(None, kickoff),
the TimeoutError is raised in the caller but the worker thread keeps running.

Solution: execute the crew inside a child process spawned with the 'spawn' context.
On timeout we call proc.terminate() / proc.kill() which the OS honors regardless
of what the process is doing.

Target functions (run_*_crew_subprocess) must be defined at module level so they
are picklable under the spawn context.
"""

from __future__ import annotations

import multiprocessing
import queue as _queue_mod
import asyncio
import json
import traceback
from typing import Callable, Any, Tuple

from app.utils.logger import get_logger
from app.utils.exceptions import CrewExecutionError

logger = get_logger(__name__)


def _subprocess_entry(target_name: str, args_json: str, result_queue) -> None:
    """Child-process entry point. Dispatches to a named target function.

    We intentionally pass `target_name` as a string (not the callable itself)
    because the top-level target functions live in this same module, avoiding
    the need to pickle arbitrary callables.
    """
    try:
        # Deferred imports so heavyweight modules (CrewAI, yfinance) only load
        # inside the child process, not the parent asyncio loop.
        targets = {
            "stock_crew": _run_stock_crew_inner,
            "fund_crew": _run_fund_crew_inner,
            "chat_crew": _run_chat_crew_inner,
        }
        fn = targets.get(target_name)
        if fn is None:
            result_queue.put(("err", f"Unknown target: {target_name}"))
            return
        args = json.loads(args_json)
        result_json = fn(**args)
        result_queue.put(("ok", result_json))
    except Exception as e:  # noqa: BLE001 - we want to report anything
        tb = traceback.format_exc()
        result_queue.put(("err", f"{type(e).__name__}: {e}\n{tb}"))


async def run_with_cancellation(
    target_name: str,
    args: dict,
    timeout: int,
) -> str:
    """Run a named crew target in a subprocess with hard cancellation.

    Args:
        target_name: one of "stock_crew", "fund_crew", "chat_crew".
        args: JSON-serializable kwargs forwarded to the target function.
        timeout: seconds before the subprocess is terminated.

    Returns:
        JSON string produced by the target function (expected to be a
        `model_dump_json()` of a Pydantic output model).

    Raises:
        asyncio.TimeoutError: subprocess exceeded timeout and was killed.
        CrewExecutionError: subprocess raised an exception.
    """
    ctx = multiprocessing.get_context("spawn")
    result_queue = ctx.Queue(maxsize=1)
    args_json = json.dumps(args)
    proc = ctx.Process(
        target=_subprocess_entry,
        args=(target_name, args_json, result_queue),
        daemon=True,
    )
    proc.start()
    logger.info(f"crew_runner: started pid={proc.pid} target={target_name} timeout={timeout}s")

    loop = asyncio.get_event_loop()

    def _blocking_get():
        try:
            return result_queue.get(timeout=timeout)
        except _queue_mod.Empty:
            return ("timeout", None)

    try:
        status, payload = await asyncio.wait_for(
            loop.run_in_executor(None, _blocking_get),
            timeout=timeout + 5,
        )
    except asyncio.TimeoutError:
        status, payload = "timeout", None

    if status == "timeout":
        logger.warning(f"crew_runner: timeout on pid={proc.pid}, terminating")
        _hard_kill(proc)
        raise asyncio.TimeoutError(f"Crew subprocess exceeded {timeout}s")

    # Drain proc cleanly in a short window
    proc.join(timeout=3)
    if proc.is_alive():
        logger.warning(f"crew_runner: pid={proc.pid} still alive after join, killing")
        _hard_kill(proc)

    if status == "err":
        raise CrewExecutionError(f"Crew subprocess failed: {payload}")
    return payload  # type: ignore[return-value]


def _hard_kill(proc) -> None:
    """Terminate → join(2s) → kill → join(1s). Best-effort, always returns."""
    try:
        proc.terminate()
        proc.join(timeout=2)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=1)
    except Exception as e:  # noqa: BLE001
        logger.error(f"crew_runner: hard kill failed: {e}")


# ---------------------------------------------------------------------------
# Target functions — executed inside the child process.
# These are placeholders filled in by Phase 5.
# ---------------------------------------------------------------------------

def _run_stock_crew_inner(**kwargs) -> str:
    raise NotImplementedError("Will be implemented in Phase 5, Task 5.1")


def _run_fund_crew_inner(**kwargs) -> str:
    raise NotImplementedError("Will be implemented in Phase 5, Task 5.2")


def _run_chat_crew_inner(**kwargs) -> str:
    raise NotImplementedError("Will be implemented in Phase 5, Task 5.3")
```

- [ ] **Step 2: Verify the module imports**

Run: `python -c "from app.services.crew_runner import run_with_cancellation; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/crew_runner.py
git commit -m "feat(backend): add crew_runner scaffolding for cancellable execution"
```

### Task 1.2: Write failing tests for `run_with_cancellation`

**Files:**
- Create: `backend/tests/test_crew_runner.py`

- [ ] **Step 1: Write the test file**

```python
"""Tests for the cancellable subprocess crew runner."""
import asyncio
import json
import pytest
from unittest.mock import patch

from app.services.crew_runner import run_with_cancellation
from app.utils.exceptions import CrewExecutionError


# A fake target function that the test patches in.
def _fake_fast(**kwargs) -> str:
    return json.dumps({"echo": kwargs, "status": "done"})


def _fake_slow(**kwargs) -> str:
    import time
    time.sleep(10)
    return "never"


def _fake_raise(**kwargs) -> str:
    raise ValueError("boom from child")


async def test_run_with_cancellation_returns_result_on_success():
    """Happy path: child returns a value quickly."""
    with patch("app.services.crew_runner._run_stock_crew_inner", _fake_fast):
        result = await run_with_cancellation(
            target_name="stock_crew",
            args={"sector": "Technology", "market": "US"},
            timeout=10,
        )
    parsed = json.loads(result)
    assert parsed["status"] == "done"
    assert parsed["echo"]["sector"] == "Technology"


async def test_run_with_cancellation_times_out_and_kills_subprocess():
    """Timeout must raise asyncio.TimeoutError, not hang."""
    with patch("app.services.crew_runner._run_stock_crew_inner", _fake_slow):
        with pytest.raises(asyncio.TimeoutError):
            await run_with_cancellation(
                target_name="stock_crew",
                args={},
                timeout=2,
            )


async def test_run_with_cancellation_surfaces_child_exception():
    """Errors inside child subprocess must raise CrewExecutionError in parent."""
    with patch("app.services.crew_runner._run_stock_crew_inner", _fake_raise):
        with pytest.raises(CrewExecutionError, match="boom from child"):
            await run_with_cancellation(
                target_name="stock_crew",
                args={},
                timeout=5,
            )


async def test_run_with_cancellation_unknown_target_errors():
    """Unknown target_name must raise CrewExecutionError."""
    with pytest.raises(CrewExecutionError, match="Unknown target"):
        await run_with_cancellation(
            target_name="not_a_real_target",
            args={},
            timeout=5,
        )
```

- [ ] **Step 2: Run tests — they should fail initially**

Run: `python -m pytest tests/test_crew_runner.py -v`

Expected: the happy-path and timeout tests FAIL, because `patch` replaces the in-process name but the subprocess re-imports the module and gets the real (NotImplementedError) function. This confirms we need Step 3.

> **Note for implementer:** On Windows+spawn, child processes re-import `app.services.crew_runner` from disk, so monkey-patches applied in the parent do NOT reach the child. We fix this in Step 3 by letting the child dispatch via an env-var override when running under pytest.

- [ ] **Step 3: Add a test-only override mechanism**

Edit `backend/app/services/crew_runner.py`:

Find `_subprocess_entry` and modify it to support a test override. Replace the whole function with:

```python
def _subprocess_entry(target_name: str, args_json: str, result_queue) -> None:
    """Child-process entry point. Dispatches to a named target function.

    Test hook: if env var CREW_RUNNER_TEST_TARGET is set, it overrides the
    dispatch map with an importable "module:func" reference so unit tests
    can inject fake fast/slow/erroring targets.
    """
    import os
    try:
        override = os.environ.get("CREW_RUNNER_TEST_TARGET")
        if override:
            mod_name, fn_name = override.split(":")
            import importlib
            fn = getattr(importlib.import_module(mod_name), fn_name)
        else:
            targets = {
                "stock_crew": _run_stock_crew_inner,
                "fund_crew": _run_fund_crew_inner,
                "chat_crew": _run_chat_crew_inner,
            }
            fn = targets.get(target_name)
            if fn is None:
                result_queue.put(("err", f"Unknown target: {target_name}"))
                return
        args = json.loads(args_json)
        result_json = fn(**args)
        result_queue.put(("ok", result_json))
    except Exception as e:
        tb = traceback.format_exc()
        result_queue.put(("err", f"{type(e).__name__}: {e}\n{tb}"))
```

- [ ] **Step 4: Rewrite the tests to use env-var override + real module-level fake targets**

Replace the full content of `backend/tests/test_crew_runner.py` with:

```python
"""Tests for the cancellable subprocess crew runner."""
import asyncio
import json
import os
import pytest
from unittest.mock import patch

from app.services.crew_runner import run_with_cancellation
from app.utils.exceptions import CrewExecutionError


# These MUST be module-level and importable so the spawned subprocess can
# re-import them after resolving CREW_RUNNER_TEST_TARGET.
def fake_fast(**kwargs) -> str:
    return json.dumps({"echo": kwargs, "status": "done"})


def fake_slow(**kwargs) -> str:
    import time
    time.sleep(30)
    return "never"


def fake_raise(**kwargs) -> str:
    raise ValueError("boom from child")


@pytest.fixture
def use_fake_target():
    """Set CREW_RUNNER_TEST_TARGET for the duration of one test."""
    originals = {}

    def _set(target: str):
        originals.setdefault("CREW_RUNNER_TEST_TARGET", os.environ.get("CREW_RUNNER_TEST_TARGET"))
        os.environ["CREW_RUNNER_TEST_TARGET"] = target

    yield _set

    if originals.get("CREW_RUNNER_TEST_TARGET") is None:
        os.environ.pop("CREW_RUNNER_TEST_TARGET", None)
    else:
        os.environ["CREW_RUNNER_TEST_TARGET"] = originals["CREW_RUNNER_TEST_TARGET"]


async def test_run_with_cancellation_returns_result_on_success(use_fake_target):
    use_fake_target("tests.test_crew_runner:fake_fast")
    result = await run_with_cancellation(
        target_name="stock_crew",
        args={"sector": "Technology", "market": "US"},
        timeout=15,
    )
    parsed = json.loads(result)
    assert parsed["status"] == "done"
    assert parsed["echo"]["sector"] == "Technology"


async def test_run_with_cancellation_times_out_and_kills_subprocess(use_fake_target):
    use_fake_target("tests.test_crew_runner:fake_slow")
    with pytest.raises(asyncio.TimeoutError):
        await run_with_cancellation(
            target_name="stock_crew",
            args={},
            timeout=2,
        )


async def test_run_with_cancellation_surfaces_child_exception(use_fake_target):
    use_fake_target("tests.test_crew_runner:fake_raise")
    with pytest.raises(CrewExecutionError, match="boom from child"):
        await run_with_cancellation(
            target_name="stock_crew",
            args={},
            timeout=10,
        )


async def test_run_with_cancellation_unknown_target_errors():
    # No env override — dispatch map is used and "not_a_real" is unknown.
    with pytest.raises(CrewExecutionError, match="Unknown target"):
        await run_with_cancellation(
            target_name="not_a_real_target",
            args={},
            timeout=10,
        )
```

- [ ] **Step 5: Run the tests — all four must pass**

Run: `python -m pytest tests/test_crew_runner.py -v`
Expected: 4 passed in ~10s. If the timeout test is flaky on your machine, bump the `timeout=2` to `timeout=3`. If `tests` is not importable as a package, add `backend/tests/__init__.py` (empty file) and re-run.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/crew_runner.py backend/tests/test_crew_runner.py
git commit -m "test(backend): cover crew_runner happy-path, timeout, error, unknown-target"
```

---

## Phase 2 — Deterministic Data Fetchers

**Why:** The pre-fetch architecture depends on Python fetching all data before the LLM sees anything. Build the fetchers first with tests; wire them in during Phase 5.

### Task 2.1: Create `data_fetchers.py` with stub functions

**Files:**
- Create: `backend/app/services/data_fetchers.py`

- [ ] **Step 1: Write the module**

```python
"""
Deterministic data fetchers — pure Python, no LLM, no crews.

These replace tool calls that free-tier LLMs cannot reliably drive.
The output dicts are small, JSON-serializable, and flow into task
descriptions as prefetched context.
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
import yfinance as yf

from app.crew.tools.sector_analysis import (
    US_SECTOR_ETFS,
    INDIA_SECTOR_INDICES,
    SectorStocksMapperTool,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


def fetch_sector_stocks_sync(sector: str, market: str, timeframe: str) -> List[Dict[str, Any]]:
    """Fetch a per-stock metric dict for every stock yfinance-mapped to a sector.

    Returns a JSON-serializable list of dicts — at most 10 per sector.
    Each dict contains symbol, name, price, currency, change_pct, pe_ratio,
    eps, roe, market_cap, debt_to_equity. Missing values become None.
    """
    mapper = SectorStocksMapperTool()
    symbols = mapper._get_sector_stocks(sector, market)
    if not symbols:
        logger.warning(f"fetch_sector_stocks_sync: no symbols for {sector}/{market}")
        return []

    return _fetch_many_stocks(symbols[:10], timeframe)


def fetch_sector_etfs_sync(sector: str, market: str, timeframe: str) -> List[Dict[str, Any]]:
    """Fetch metric dicts for the primary sector ETF/index and up to 2 peers.

    For US, uses the SPDR sector ETFs (XLK, XLF, ...). For India, uses Nifty
    sectoral indices. Returns up to 3 dicts.
    """
    etf_map = US_SECTOR_ETFS if market == "US" else INDIA_SECTOR_INDICES
    primary = etf_map.get(sector)
    if not primary:
        logger.warning(f"fetch_sector_etfs_sync: no ETF mapping for {sector}/{market}")
        return []

    peers = [s for s in etf_map.values() if s != primary][:2]
    symbols = [primary] + peers
    return _fetch_many_stocks(symbols, timeframe, as_fund=True)


def fetch_stock_snapshot_sync(symbol: str, timeframe: str = "30d") -> Dict[str, Any]:
    """Fetch a single stock's snapshot dict. Returns {} on failure."""
    rows = _fetch_many_stocks([symbol], timeframe)
    return rows[0] if rows else {}


def fetch_stock_news_sync(symbol: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Fetch recent news headlines for a symbol via yfinance.

    Returns a list of {"title", "publisher", "link", "date"} dicts.
    Safe to call during chat flows — no news provider means empty list.
    """
    try:
        raw = yf.Ticker(symbol).news or []
    except Exception as e:  # noqa: BLE001
        logger.warning(f"fetch_stock_news_sync failed for {symbol}: {e}")
        return []

    items: List[Dict[str, Any]] = []
    for entry in raw[:limit]:
        try:
            items.append({
                "title": entry.get("title", ""),
                "publisher": entry.get("publisher", ""),
                "link": entry.get("link", ""),
                "date": entry.get("providerPublishTime", ""),
            })
        except Exception:
            continue
    return items


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _fetch_many_stocks(
    symbols: List[str],
    timeframe: str,
    as_fund: bool = False,
) -> List[Dict[str, Any]]:
    """Batch-fetch yfinance data for many symbols.

    Returns a list of dicts. Missing values are coerced to None so the JSON
    is clean for Pydantic consumption downstream.
    """
    period_map = {"7d": "7d", "30d": "1mo", "90d": "3mo"}
    period = period_map.get(timeframe, "1mo")

    try:
        hist_data = yf.download(
            symbols, period=period, auto_adjust=True,
            progress=False, threads=True,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"_fetch_many_stocks: batch download failed: {e}")
        hist_data = None

    results: List[Dict[str, Any]] = []
    for symbol in symbols:
        try:
            info = yf.Ticker(symbol).info or {}
            change_pct = _safe_change_pct(hist_data, symbol, len(symbols))
            currency = "INR" if (".NS" in symbol or ".BO" in symbol) else "USD"
            roe_raw = info.get("returnOnEquity")
            row: Dict[str, Any] = {
                "symbol": symbol,
                "name": info.get("longName") or info.get("shortName") or symbol,
                "price": _coerce_float(info.get("currentPrice")),
                "currency": currency,
                "change_pct": round(change_pct, 2),
                "pe_ratio": _coerce_float(info.get("trailingPE")),
                "eps": _coerce_float(info.get("trailingEps")),
                "roe": round(roe_raw * 100, 1) if isinstance(roe_raw, (int, float)) else None,
                "market_cap": _coerce_float(info.get("marketCap")),
                "debt_to_equity": _coerce_float(info.get("debtToEquity")),
            }
            if as_fund:
                row["expense_ratio"] = _coerce_float(info.get("annualReportExpenseRatio"))
                row["aum"] = _coerce_float(info.get("totalAssets"))
            results.append(row)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"_fetch_many_stocks: skip {symbol}: {e}")
            continue
    return results


def _safe_change_pct(hist_data, symbol: str, n_symbols: int) -> float:
    if hist_data is None or getattr(hist_data, "empty", True):
        return 0.0
    try:
        close = hist_data["Close"]
        col = close if n_symbols == 1 else close[symbol]
        col = col.dropna()
        if len(col) >= 2:
            return float((col.iloc[-1] - col.iloc[0]) / col.iloc[0] * 100)
    except (KeyError, TypeError):
        pass
    return 0.0


def _coerce_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 2: Verify import**

Run: `python -c "from app.services.data_fetchers import fetch_sector_stocks_sync; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/data_fetchers.py
git commit -m "feat(backend): add deterministic data_fetchers module"
```

### Task 2.2: Write tests for `data_fetchers`

**Files:**
- Create: `backend/tests/test_data_fetchers.py`

- [ ] **Step 1: Write the test file**

```python
"""Unit tests for deterministic data fetchers.

All yfinance calls are mocked — these tests must be fast and offline.
"""
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from app.services.data_fetchers import (
    fetch_sector_stocks_sync,
    fetch_sector_etfs_sync,
    fetch_stock_snapshot_sync,
    fetch_stock_news_sync,
)


def _mock_ticker(info: dict, news=None):
    m = MagicMock()
    m.info = info
    m.news = news or []
    return m


def test_fetch_sector_stocks_returns_dict_list_with_required_fields():
    fake_info = {
        "longName": "Apple Inc.",
        "currentPrice": 175.5,
        "trailingPE": 28.5,
        "trailingEps": 6.13,
        "returnOnEquity": 0.35,
        "marketCap": 2_800_000_000_000,
        "debtToEquity": 1.8,
    }
    with patch("app.services.data_fetchers.yf.Ticker", return_value=_mock_ticker(fake_info)), \
         patch("app.services.data_fetchers.yf.download", return_value=pd.DataFrame()):
        rows = fetch_sector_stocks_sync("Technology", "US", "30d")

    assert isinstance(rows, list)
    assert len(rows) > 0
    row = rows[0]
    for key in ("symbol", "name", "price", "currency", "change_pct",
                "pe_ratio", "eps", "roe", "market_cap", "debt_to_equity"):
        assert key in row
    assert row["name"] == "Apple Inc."
    assert row["roe"] == 35.0  # returnOnEquity 0.35 -> 35.0%
    assert row["currency"] == "USD"


def test_fetch_sector_stocks_unknown_sector_returns_empty():
    rows = fetch_sector_stocks_sync("NotARealSector", "US", "30d")
    assert rows == []


def test_fetch_sector_stocks_india_detects_inr_currency():
    fake_info = {"longName": "Reliance", "currentPrice": 2500.0}
    with patch("app.services.data_fetchers.yf.Ticker", return_value=_mock_ticker(fake_info)), \
         patch("app.services.data_fetchers.yf.download", return_value=pd.DataFrame()):
        rows = fetch_sector_stocks_sync("Technology", "IN", "30d")

    assert any(r["currency"] == "INR" for r in rows)


def test_fetch_sector_etfs_returns_primary_plus_peers():
    fake_info = {"longName": "Tech SPDR", "currentPrice": 195.0}
    with patch("app.services.data_fetchers.yf.Ticker", return_value=_mock_ticker(fake_info)), \
         patch("app.services.data_fetchers.yf.download", return_value=pd.DataFrame()):
        rows = fetch_sector_etfs_sync("Technology", "US", "30d")

    assert len(rows) <= 3
    assert len(rows) > 0
    # First row should be the XLK primary (from US_SECTOR_ETFS)
    assert rows[0]["symbol"] == "XLK"
    # Fund-shaped rows include expense_ratio/aum keys even if None
    assert "expense_ratio" in rows[0]
    assert "aum" in rows[0]


def test_fetch_stock_snapshot_single_symbol():
    fake_info = {"longName": "MSFT", "currentPrice": 410.0, "trailingPE": 35.0}
    with patch("app.services.data_fetchers.yf.Ticker", return_value=_mock_ticker(fake_info)), \
         patch("app.services.data_fetchers.yf.download", return_value=pd.DataFrame()):
        snap = fetch_stock_snapshot_sync("MSFT", "30d")

    assert snap["symbol"] == "MSFT"
    assert snap["price"] == 410.0
    assert snap["pe_ratio"] == 35.0


def test_fetch_stock_news_returns_parsed_dicts():
    news_raw = [
        {"title": "Big News", "publisher": "Reuters",
         "link": "http://x", "providerPublishTime": 1710000000},
        {"title": "Other", "publisher": "Bloomberg",
         "link": "http://y", "providerPublishTime": 1710000001},
    ]
    with patch("app.services.data_fetchers.yf.Ticker",
               return_value=_mock_ticker({}, news=news_raw)):
        items = fetch_stock_news_sync("AAPL", limit=5)

    assert len(items) == 2
    assert items[0]["title"] == "Big News"
    assert items[0]["publisher"] == "Reuters"


def test_fetch_stock_news_handles_yfinance_error_gracefully():
    with patch("app.services.data_fetchers.yf.Ticker",
               side_effect=Exception("network down")):
        items = fetch_stock_news_sync("AAPL")
    assert items == []
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/test_data_fetchers.py -v`
Expected: all 7 tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_data_fetchers.py
git commit -m "test(backend): cover data_fetchers (sector stocks, ETFs, snapshot, news)"
```

---

## Phase 3 — Task Redesign

**Goal:** Rewrite tasks to take prefetched data via `description` (not tools) and return structured JSON via `output_pydantic`. Delete reflection tasks.

### Task 3.1: Rewrite `find_top_stocks_in_sector` to accept prefetched data

**Files:**
- Modify: `backend/app/crew/tasks.py:117-172`

- [ ] **Step 1: Replace the function**

Find the `find_top_stocks_in_sector` staticmethod (lines 116–172) and replace the entire function with:

```python
    @staticmethod
    def find_top_stocks_in_sector(
        agent,
        sector: str,
        market: str,
        timeframe: str,
        prefetched_stocks: list,
    ) -> Task:
        """Task: Rank the top 3 stocks from a PRE-FETCHED list.

        The agent does NOT call tools. All financial data is already embedded
        in the task description as a JSON list. The agent's sole job is to
        pick the top 3 and output the required Pydantic schema.
        """
        import json as _json
        data_block = _json.dumps(prefetched_stocks, indent=2, default=str)
        return Task(
            description=f"""You are given a list of pre-fetched stocks in the {sector} sector
of the {market} market over the {timeframe} timeframe. All prices, P/E ratios, EPS, ROE,
market cap, and debt/equity values below are already correct — do NOT call any tools.

PREFETCHED STOCK DATA (JSON):
{data_block}

Your task:
1. From this list ONLY, pick the 3 best stocks, ranked by a blended view of:
   - change_pct over {timeframe} (recent momentum)
   - pe_ratio and eps (valuation)
   - roe (quality)
   - market_cap (stability — larger is safer)
2. For each pick, write a 2–3 sentence "reasoning" string that cites specific
   numbers from the data block above (e.g. "P/E of 28.5 with +5.2% over 30d").
3. Output the final JSON object matching the schema below and NOTHING ELSE.

Sector: {sector}
Market: {market}
Timeframe: {timeframe}

CRITICAL OUTPUT RULES:
- Your FINAL answer must be ONLY a valid JSON object matching the schema.
- Do NOT wrap the JSON in markdown fences.
- Do NOT include any "thought", "action", "observation", or "Final Answer:" prefix.
- Do NOT call any tools — you have none.
""",
            expected_output=f"""A JSON object exactly matching this schema:
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
      "reasoning": "2-3 sentence explanation citing specific metrics",
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
Exactly 3 stocks. Numeric fields must be numbers, not strings. Use null where data is missing.""",
            agent=agent,
            output_pydantic=SectorStocksOutput,
        )
```

### Task 3.2: Rewrite `identify_top_etfs_in_sector` to accept prefetched data

**Files:**
- Modify: `backend/app/crew/tasks.py:326-392` (the `identify_top_etfs_in_sector` function)

- [ ] **Step 1: Replace the function**

Find `identify_top_etfs_in_sector` (starts around line 327) and replace the entire function with:

```python
    @staticmethod
    def identify_top_etfs_in_sector(
        agent,
        sector: str,
        market: str,
        timeframe: str,
        prefetched_etfs: list,
    ) -> Task:
        """Task: Rank the top 3 ETFs/funds from a PRE-FETCHED list. No tools used."""
        import json as _json
        currency = "USD" if market == "US" else "INR"
        data_block = _json.dumps(prefetched_etfs, indent=2, default=str)
        return Task(
            description=f"""You are given pre-fetched ETF / sector-index data for the {sector}
sector of the {market} market over the {timeframe} timeframe. All NAV, expense ratios,
AUM, and % change values are already correct — do NOT call any tools.

PREFETCHED FUND DATA (JSON):
{data_block}

Your task:
1. From this list ONLY, pick the 3 best funds ranked by change_pct, expense_ratio
   (lower is better), and market_cap / aum (larger is more liquid).
2. For each pick, write a 2–3 sentence reasoning that cites the specific numbers.
3. Output the final JSON object matching the schema below and NOTHING ELSE.

Sector: {sector}
Market: {market}
Timeframe: {timeframe}
Currency: {currency}

CRITICAL OUTPUT RULES:
- Your FINAL answer must be ONLY a valid JSON object matching the schema.
- Do NOT wrap the JSON in markdown fences.
- Do NOT include any ReAct-format fields (thought/action/observation).
- Do NOT call any tools — you have none.
""",
            expected_output=f"""A JSON object exactly matching this schema:
{{
  "sector": "{sector}",
  "market": "{market}",
  "funds": [
    {{
      "symbol": "XLK",
      "name": "Full ETF name",
      "current_nav": 195.0,
      "currency": "{currency}",
      "expense_ratio": 0.13,
      "aum": "$50B",
      "change_percent": 3.2,
      "recommendation_score": 8.5,
      "reasoning": "2-3 sentence explanation citing specific performance figures"
    }}
  ]
}}
Exactly 3 funds. Set expense_ratio and aum to null if not in the data. Numeric fields must be numbers.""",
            agent=agent,
            output_pydantic=SectorFundsOutput,
        )
```

### Task 3.3: Rewrite `synthesize_chat_response` to accept prefetched data directly

**Files:**
- Modify: `backend/app/crew/tasks.py:228-267` (the `synthesize_chat_response` function)

- [ ] **Step 1: Replace the function**

Find `synthesize_chat_response` and replace it with:

```python
    @staticmethod
    def synthesize_chat_response(
        agent,
        user_question: str,
        stock_symbol: str,
        market: str,
        prefetched_snapshot: dict,
        prefetched_news: list,
    ) -> Task:
        """Task: Answer user's question using ONLY the prefetched data. No tools."""
        import json as _json
        snapshot_block = _json.dumps(prefetched_snapshot or {}, indent=2, default=str)
        news_block = _json.dumps(prefetched_news or [], indent=2, default=str)

        return Task(
            description=f"""Answer the user's question about {stock_symbol} using ONLY the
pre-fetched data below. Do NOT call any tools.

User Question: "{user_question}"
Stock Symbol: {stock_symbol}
Market: {market}

PREFETCHED STOCK SNAPSHOT (JSON):
{snapshot_block}

PREFETCHED NEWS (JSON):
{news_block}

Your approach:
1. Read the snapshot and news above.
2. Write a 200–400 word conversational answer that cites specific numbers from the snapshot.
3. Build the `sources` list from the news titles and links above.
4. Fill `agent_reasoning` with a one-line explanation of your logic.

CRITICAL OUTPUT RULES:
- Return ONLY the JSON object matching the schema below.
- Do NOT wrap it in markdown fences.
- Do NOT include ReAct-format fields.
- Do NOT call any tools — you have none.
""",
            expected_output=f"""A JSON object exactly matching this schema:
{{
  "response": "Your conversational answer (200-400 words) citing specific numbers",
  "sources": [
    {{
      "title": "Article title from prefetched news",
      "url": "https://source-url.com",
      "date": "YYYY-MM-DD"
    }}
  ],
  "agent_reasoning": "One-line explanation of how you arrived at this answer"
}}
`sources` may be an empty list if prefetched_news was empty.""",
            agent=agent,
            output_pydantic=ChatAnswerOutput,
        )
```

### Task 3.4: Delete `reflect_on_stock_picks` and `reflect_on_fund_picks`

- [ ] **Step 1: Remove the two reflection functions**

In `backend/app/crew/tasks.py`:
- Delete the entire `reflect_on_stock_picks` function (originally lines 174–225).
- Delete the entire `reflect_on_fund_picks` function (originally lines 394–441).

- [ ] **Step 2: Remove legacy `analyze_stock_financials` and `research_stock_news`**

These tool-driven chat tasks are replaced by the prefetch flow. In `backend/app/crew/tasks.py`:
- Delete the entire `research_stock_news` function (originally lines 15–43).
- Delete the entire `analyze_stock_financials` function (originally lines 46–78).
- Delete the entire `create_comprehensive_recommendation` function (originally lines 269–324) — it is never called anywhere.

- [ ] **Step 3: Remove unused `identify_top_sectors` task**

`recommendations_service.py` uses the direct yfinance path (`_get_top_sectors_direct`) already. The crew-based sector task is dead code.
- Delete the entire `identify_top_sectors` function (originally lines 81–114).

- [ ] **Step 4: Verify imports at top of tasks.py are still needed**

Open the file and confirm the imports section at the top only references what remains:

```python
from crewai import Task
from app.crew.output_models import (
    SectorStocksOutput,
    ChatAnswerOutput,
    SectorFundsOutput,
)
```

Remove unused imports (`SectorRankingOutput`, `List`, `datetime`) if no longer referenced in the file.

- [ ] **Step 5: Syntax-check the file**

Run: `python -c "from app.crew.tasks import FinancialTasks; print(dir(FinancialTasks))"`
Expected: prints a list that includes `find_top_stocks_in_sector`, `identify_top_etfs_in_sector`, `synthesize_chat_response`, and NOT `reflect_on_stock_picks`, `research_stock_news`, `analyze_stock_financials`, `identify_top_sectors`, `create_comprehensive_recommendation`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/crew/tasks.py
git commit -m "refactor(backend): replace tool-driven tasks with prefetched-data tasks"
```

---

## Phase 4 — Agent Simplification

### Task 4.1: Strip tools and lower `max_iter` on the two crew agents

**Files:**
- Modify: `backend/app/crew/agents.py:97-130` (financial_data_analyst) and `backend/app/crew/agents.py:173-223` (investment_advisor)

- [ ] **Step 1: Replace `financial_data_analyst`**

Find `def financial_data_analyst()` and replace the whole function with:

```python
    @staticmethod
    def financial_data_analyst() -> Agent:
        """Agent 2: Reasons over pre-fetched stock data. NO tools, max_iter=2."""
        return Agent(
            role="Quantitative Financial Metrics Specialist",
            goal="Rank pre-fetched stocks by the metrics supplied in the task and output strict JSON",
            backstory="""You are a quantitative analyst. Every piece of financial data you
            need — prices, P/E ratios, ROE, market cap, debt/equity — is handed to you
            inside each task description as a JSON block. Your ONLY job is to read that
            block, rank the candidates, and output the exact JSON schema requested.

            You never call tools. You never invent data. If a field is null in the
            input, you output it as null. You never output ReAct-format text; your
            final answer is always pure JSON.""",
            tools=[],
            llm=get_llm(temperature=0.2),
            verbose=True,
            allow_delegation=False,
            max_iter=2,
        )
```

- [ ] **Step 2: Replace `investment_advisor`**

Find `def investment_advisor()` and replace the whole function with:

```python
    @staticmethod
    def investment_advisor() -> Agent:
        """Agent 4: Synthesizes prefetched data into a conversational answer. NO tools, max_iter=2."""
        return Agent(
            role="Chief Investment Strategist and Recommendation Synthesizer",
            goal="Answer user questions using only the pre-fetched context and output strict JSON",
            backstory="""You are a CIO with 20 years of experience. You never call tools —
            every piece of data you need, including stock snapshots and news articles,
            is already embedded in the task description.

            You read the prefetched context carefully, cite specific numbers in your
            answer, and always return the exact JSON schema requested. You never output
            ReAct-format fields and never invent data.""",
            tools=[],
            llm=get_llm(temperature=0.4),
            verbose=True,
            allow_delegation=False,
            max_iter=2,
        )
```

- [ ] **Step 3: Leave `market_researcher` and `sector_performance_analyst` alone**

These are no longer used by any crew flow (chat uses prefetched news directly; sector ranking uses `_get_top_sectors_direct`). We leave the factory methods in place for now — they are imported by the test file. Phase 7 Task 7.1 will relax the related tests.

- [ ] **Step 4: Verify module imports**

Run: `python -c "from app.crew.agents import FinancialAgents; a = FinancialAgents.financial_data_analyst(); print('tools:', len(a.tools), 'max_iter:', a.max_iter)"`
Expected: `tools: 0 max_iter: 2`

- [ ] **Step 5: Commit**

```bash
git add backend/app/crew/agents.py
git commit -m "refactor(backend): strip tools and set max_iter=2 on crew agents"
```

---

## Phase 5 — Service Wiring

### Task 5.1: Implement `_run_stock_crew_inner` inside `crew_runner.py`

**Files:**
- Modify: `backend/app/services/crew_runner.py`

- [ ] **Step 1: Replace the `_run_stock_crew_inner` stub**

Find the stub and replace it with:

```python
def _run_stock_crew_inner(
    sector: str,
    market: str,
    timeframe: str,
    prefetched_stocks: list,
) -> str:
    """Build and run a stock-picking crew inside the child process.

    Returns a JSON string of SectorStocksOutput.
    """
    from crewai import Crew, Process
    from app.crew.agents import FinancialAgents
    from app.crew.tasks import FinancialTasks
    from app.crew.output_models import SectorStocksOutput

    data_analyst = FinancialAgents.financial_data_analyst()
    stock_task = FinancialTasks.find_top_stocks_in_sector(
        data_analyst, sector, market, timeframe, prefetched_stocks
    )
    crew = Crew(
        agents=[data_analyst],
        tasks=[stock_task],
        process=Process.sequential,
        verbose=False,
        memory=False,
        cache=False,
    )
    result = crew.kickoff()
    output = result.pydantic
    if output is None:
        output = SectorStocksOutput.model_validate_json(result.raw)
    return output.model_dump_json()
```

### Task 5.2: Implement `_run_fund_crew_inner`

- [ ] **Step 1: Replace the stub**

```python
def _run_fund_crew_inner(
    sector: str,
    market: str,
    timeframe: str,
    prefetched_etfs: list,
) -> str:
    """Build and run a fund-picking crew inside the child process."""
    from crewai import Crew, Process
    from app.crew.agents import FinancialAgents
    from app.crew.tasks import FinancialTasks
    from app.crew.output_models import SectorFundsOutput

    data_analyst = FinancialAgents.financial_data_analyst()
    etf_task = FinancialTasks.identify_top_etfs_in_sector(
        data_analyst, sector, market, timeframe, prefetched_etfs
    )
    crew = Crew(
        agents=[data_analyst],
        tasks=[etf_task],
        process=Process.sequential,
        verbose=False,
        memory=False,
        cache=False,
    )
    result = crew.kickoff()
    output = result.pydantic
    if output is None:
        output = SectorFundsOutput.model_validate_json(result.raw)
    return output.model_dump_json()
```

### Task 5.3: Implement `_run_chat_crew_inner`

- [ ] **Step 1: Replace the stub**

```python
def _run_chat_crew_inner(
    user_question: str,
    stock_symbol: str,
    market: str,
    prefetched_snapshot: dict,
    prefetched_news: list,
) -> str:
    """Build and run a chat-synthesis crew inside the child process."""
    from crewai import Crew, Process
    from app.crew.agents import FinancialAgents
    from app.crew.tasks import FinancialTasks
    from app.crew.output_models import ChatAnswerOutput

    advisor = FinancialAgents.investment_advisor()
    chat_task = FinancialTasks.synthesize_chat_response(
        advisor, user_question, stock_symbol, market,
        prefetched_snapshot, prefetched_news,
    )
    crew = Crew(
        agents=[advisor],
        tasks=[chat_task],
        process=Process.sequential,
        verbose=False,
        memory=False,
        cache=False,
    )
    result = crew.kickoff()
    output = result.pydantic
    if output is None:
        output = ChatAnswerOutput.model_validate_json(result.raw)
    return output.model_dump_json()
```

- [ ] **Step 2: Verify module still imports**

Run: `python -c "from app.services.crew_runner import _run_stock_crew_inner, _run_fund_crew_inner, _run_chat_crew_inner; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/crew_runner.py
git commit -m "feat(backend): implement crew_runner inner functions for stock/fund/chat"
```

### Task 5.4: Rewrite `RecommendationsService._run_stock_crew_for_sector` to use prefetch + subprocess

**Files:**
- Modify: `backend/app/services/recommendations_service.py:211-257`

- [ ] **Step 1: Replace `_run_stock_crew_for_sector`**

Find the method and replace the entire body with:

```python
    async def _run_stock_crew_for_sector(
        self,
        sector_info,
        market: str,
        timeframe: str,
        rank: int,
    ) -> dict:
        """Pre-fetch sector stocks in Python, then run a crew in a subprocess."""
        from app.services.data_fetchers import fetch_sector_stocks_sync
        from app.services.crew_runner import run_with_cancellation
        from app.crew.output_models import SectorStocksOutput

        loop = asyncio.get_event_loop()
        prefetched = await loop.run_in_executor(
            None, fetch_sector_stocks_sync, sector_info.name, market, timeframe
        )
        if not prefetched:
            raise CrewExecutionError(
                f"No prefetched stock data for {sector_info.name} ({market})"
            )

        result_json = await run_with_cancellation(
            target_name="stock_crew",
            args={
                "sector": sector_info.name,
                "market": market,
                "timeframe": timeframe,
                "prefetched_stocks": prefetched,
            },
            timeout=settings.CREW_TIMEOUT_SECONDS,
        )
        stocks_output = SectorStocksOutput.model_validate_json(result_json)

        return {
            "sector": sector_info.name,
            "rank": rank,
            "performance_percent": sector_info.performance_pct,
            "region": market,
            "top_stocks": [s.model_dump() for s in stocks_output.stocks[:3]],
        }
```

### Task 5.5: Rewrite `_run_fund_crew_for_sector`

**Files:**
- Modify: `backend/app/services/recommendations_service.py:259-305`

- [ ] **Step 1: Replace the method**

```python
    async def _run_fund_crew_for_sector(
        self,
        sector_info,
        market: str,
        timeframe: str,
        rank: int,
    ) -> dict:
        """Pre-fetch sector ETFs in Python, then run a crew in a subprocess."""
        from app.services.data_fetchers import fetch_sector_etfs_sync
        from app.services.crew_runner import run_with_cancellation
        from app.crew.output_models import SectorFundsOutput

        loop = asyncio.get_event_loop()
        prefetched = await loop.run_in_executor(
            None, fetch_sector_etfs_sync, sector_info.name, market, timeframe
        )
        if not prefetched:
            raise CrewExecutionError(
                f"No prefetched ETF data for {sector_info.name} ({market})"
            )

        result_json = await run_with_cancellation(
            target_name="fund_crew",
            args={
                "sector": sector_info.name,
                "market": market,
                "timeframe": timeframe,
                "prefetched_etfs": prefetched,
            },
            timeout=settings.CREW_TIMEOUT_SECONDS,
        )
        funds_output = SectorFundsOutput.model_validate_json(result_json)

        return {
            "sector": sector_info.name,
            "rank": rank,
            "performance_percent": sector_info.performance_pct,
            "market": market,
            "top_funds": [f.model_dump() for f in funds_output.funds[:3]],
        }
```

### Task 5.6: Remove `_run_crew_with_timeout` from `RecommendationsService`

**Files:**
- Modify: `backend/app/services/recommendations_service.py:417-422`

- [ ] **Step 1: Delete the method**

Delete the entire `_run_crew_with_timeout` method at the bottom of the file.

- [ ] **Step 2: Clean up unused imports at the top**

In `recommendations_service.py`, the imports at the top can now drop `Crew`, `Process`, `FinancialAgents`, `FinancialTasks`, `SectorStocksOutput`, `SectorFundsOutput` (the per-sector methods import what they need locally). Keep `SectorRankingOutput` and `SectorInfo` (used by `_fetch_sectors_sync`).

Update the top of the file to:

```python
"""
Recommendations Service — executes stock and fund recommendation crews.

Stock recommendations: direct yfinance sector fetch → per-sector prefetched stock crew.
Fund recommendations: direct yfinance sector fetch → per-sector prefetched ETF crew.
"""

import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import uuid

from app.crew.output_models import SectorRankingOutput, SectorInfo
from app.crew.tools.sector_analysis import SectorPerformanceTool, US_SECTOR_ETFS, INDIA_SECTOR_INDICES
from app.services.job_store import JobStore
from app.config import settings
from app.utils.logger import get_logger
from app.utils.exceptions import CrewExecutionError

logger = get_logger(__name__)
```

- [ ] **Step 3: Syntax-check**

Run: `python -c "from app.services.recommendations_service import RecommendationsService; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/recommendations_service.py
git commit -m "refactor(backend): prefetch + subprocess for stock/fund sector crews"
```

### Task 5.7: Rewrite `ChatService.execute_chat_query`

**Files:**
- Modify: `backend/app/services/chat_service.py` (whole file)

- [ ] **Step 1: Replace the file content**

```python
"""
Chat Service — prefetches data, then runs a chat-synthesis crew in a subprocess.
"""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import uuid

from app.crew.output_models import ChatAnswerOutput
from app.services.job_store import JobStore
from app.services.crew_runner import run_with_cancellation
from app.services.data_fetchers import fetch_stock_snapshot_sync, fetch_stock_news_sync
from app.services.intent_classifier import classify_intent
from app.config import settings
from app.utils.logger import get_logger
from app.utils.exceptions import CrewExecutionError

logger = get_logger(__name__)


class ChatService:
    """Executes the chat crew asynchronously over pre-fetched data."""

    def __init__(self, job_store: Optional[JobStore] = None):
        self.job_store = job_store

    async def execute_chat_query(
        self,
        message: str,
        stock_symbol: str,
        market: str,
        job_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not job_id:
            job_id = str(uuid.uuid4())

        if self.job_store:
            await self.job_store.create_job(job_id, "chat")
            await self.job_store.update_job(job_id, "processing", "Classifying intent...")

        try:
            intent = await classify_intent(message)
            logger.info(f"Classified intent: {intent}")

            loop = asyncio.get_event_loop()
            snapshot: Dict[str, Any] = {}
            news: list = []

            if self.job_store:
                await self.job_store.update_job(job_id, "processing", "Fetching stock data...")

            # Always fetch the snapshot — it's cheap and grounds the response.
            snapshot = await loop.run_in_executor(
                None, fetch_stock_snapshot_sync, stock_symbol, "30d"
            )

            if intent.get("needs_news"):
                if self.job_store:
                    await self.job_store.update_job(job_id, "processing", "Fetching news...")
                news = await loop.run_in_executor(
                    None, fetch_stock_news_sync, stock_symbol, 5
                )

            if self.job_store:
                await self.job_store.update_job(job_id, "processing", "Synthesizing response...")

            result_json = await run_with_cancellation(
                target_name="chat_crew",
                args={
                    "user_question": message,
                    "stock_symbol": stock_symbol,
                    "market": market,
                    "prefetched_snapshot": snapshot,
                    "prefetched_news": news,
                },
                timeout=settings.CREW_TIMEOUT_SECONDS,
            )
            output = ChatAnswerOutput.model_validate_json(result_json)

            response_data = {
                "response": output.response,
                "sources": [s.model_dump() for s in output.sources],
                "agent_reasoning": {"investment_advisor": output.agent_reasoning},
                "stock_symbol": stock_symbol,
                "timestamp": datetime.now(timezone.utc).isoformat(),
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
```

- [ ] **Step 2: Syntax-check**

Run: `python -c "from app.services.chat_service import ChatService; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/chat_service.py
git commit -m "refactor(backend): prefetch + subprocess for chat synthesis"
```

---

## Phase 6 — Config Updates

### Task 6.1: Lower `CREW_TIMEOUT_SECONDS` default

**Files:**
- Modify: `backend/app/config.py:46`

- [ ] **Step 1: Change the default**

Find:
```python
    CREW_TIMEOUT_SECONDS: int = 240
```

Replace with:
```python
    # Per-crew subprocess hard timeout. With prefetched data and max_iter=2
    # each crew should complete in 15–30s; 90s gives generous headroom.
    CREW_TIMEOUT_SECONDS: int = 90
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/config.py
git commit -m "chore(backend): lower CREW_TIMEOUT_SECONDS to 90s for prefetch architecture"
```

---

## Phase 7 — Test Updates

### Task 7.1: Update `test_crew_service.py` to match new agent shape

**Files:**
- Modify: `backend/tests/test_crew_service.py`

- [ ] **Step 1: Delete obsolete tests**

Delete these entire tests from the file (they assert on removed tasks and old max_iter):
- `test_stock_news_task_creation`
- `test_chat_synthesis_task_creation` (signature changed, rewritten below)
- `test_find_top_stocks_task_description_guides_batch_fetch`
- `test_find_top_stocks_task_description_has_ordered_steps`
- `test_financial_data_analyst_max_iter_supports_batch_flow`
- `test_investment_advisor_max_iter_supports_reflect_flow`
- `test_crew_timeout_covers_max_iter_on_free_tier`
- `test_sector_identification_task_creation`

Also delete the PortfolioDataTool tests (`test_portfolio_data_tool_returns_per_stock_summary`, `test_portfolio_data_tool_handles_missing_symbol_gracefully`, `test_portfolio_data_tool_all_symbols_fail_returns_message`) — the tool is no longer referenced by any crew code path. Keep the file slim.

- [ ] **Step 2: Replace with new assertions**

After this cleanup the file should look like:

```python
"""Tests for agent factory and task factory (prefetch architecture)."""

from app.crew.agents import FinancialAgents
from app.crew.tasks import FinancialTasks


def test_market_researcher_agent():
    agent = FinancialAgents.market_researcher()
    assert agent.role
    assert isinstance(agent.tools, list)


def test_financial_data_analyst_has_no_tools_and_low_iter():
    """Prefetch architecture: data analyst must NOT call tools."""
    agent = FinancialAgents.financial_data_analyst()
    assert agent.tools == []
    assert agent.max_iter == 2


def test_investment_advisor_has_no_tools_and_low_iter():
    """Prefetch architecture: advisor must NOT call tools."""
    agent = FinancialAgents.investment_advisor()
    assert agent.tools == []
    assert agent.max_iter == 2


def test_find_top_stocks_task_embeds_prefetched_data():
    agent = FinancialAgents.financial_data_analyst()
    prefetched = [{
        "symbol": "AAPL", "name": "Apple Inc.", "price": 175.5,
        "currency": "USD", "change_pct": 5.2, "pe_ratio": 28.5,
        "eps": 6.13, "roe": 35.0, "market_cap": 2.8e12, "debt_to_equity": 1.8,
    }]
    task = FinancialTasks.find_top_stocks_in_sector(
        agent, "Technology", "US", "30d", prefetched
    )
    desc = task.description
    assert "PREFETCHED STOCK DATA" in desc
    assert "AAPL" in desc
    assert "175.5" in desc
    # Must not instruct tool use
    assert "Multi-Stock Data Fetcher" not in desc
    assert "Sector Stocks Finder" not in desc


def test_identify_top_etfs_task_embeds_prefetched_data():
    agent = FinancialAgents.financial_data_analyst()
    prefetched = [{
        "symbol": "XLK", "name": "Tech SPDR", "price": 195.0,
        "currency": "USD", "change_pct": 3.2,
    }]
    task = FinancialTasks.identify_top_etfs_in_sector(
        agent, "Technology", "US", "30d", prefetched
    )
    desc = task.description
    assert "PREFETCHED FUND DATA" in desc
    assert "XLK" in desc


def test_synthesize_chat_response_embeds_prefetched_context():
    agent = FinancialAgents.investment_advisor()
    snapshot = {"symbol": "MSFT", "price": 410.0, "pe_ratio": 35.0}
    news = [{"title": "Earnings beat", "publisher": "Reuters",
             "link": "http://x", "date": "2026-04-10"}]
    task = FinancialTasks.synthesize_chat_response(
        agent, "How is MSFT doing?", "MSFT", "US", snapshot, news
    )
    desc = task.description
    assert "PREFETCHED STOCK SNAPSHOT" in desc
    assert "PREFETCHED NEWS" in desc
    assert "MSFT" in desc
    assert "Earnings beat" in desc


def test_crew_timeout_default_fits_prefetch_budget():
    """Subprocess timeout should be tight now that crews have no tools."""
    from app.config import settings
    assert 60 <= settings.CREW_TIMEOUT_SECONDS <= 120
```

- [ ] **Step 3: Run these tests — all must pass**

Run: `python -m pytest tests/test_crew_service.py -v`
Expected: 8 passed.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_crew_service.py
git commit -m "test(backend): update crew tests for prefetch architecture"
```

### Task 7.2: Update `test_recommendations_service.py`

**Files:**
- Modify: `backend/tests/test_recommendations_service.py`

- [ ] **Step 1: Delete obsolete tests**

Delete the following tests — they assert on `reflect_on_stock_picks` / `reflect_on_fund_picks` / `_run_crew_with_timeout` which are gone:
- `test_sequential_crew_with_reflection_task`
- `test_run_stock_crew_none_pydantic_falls_back_to_raw`
- `test_run_stock_crew_none_pydantic_unparseable_raw_raises`
- `test_run_fund_crew_none_pydantic_falls_back_to_raw`
- `test_run_fund_crew_none_pydantic_unparseable_raw_raises`
- `test_partial_sector_failure_excluded`
- `test_all_sectors_fail_raises_error`

- [ ] **Step 2: Replace them with prefetch-path tests**

Append these tests to the file:

```python
# ---------------------------------------------------------------------------
# Prefetch architecture tests
# ---------------------------------------------------------------------------

async def test_run_stock_crew_for_sector_uses_prefetch_and_runner(service):
    """_run_stock_crew_for_sector must call fetch_sector_stocks_sync then run_with_cancellation."""
    sector_info = SectorInfo(
        name="Technology", performance_pct=12.5,
        trend="Up", momentum="High", drivers="AI"
    )
    prefetched = [{"symbol": "AAPL", "name": "Apple", "price": 175.0}]

    valid_output_json = SectorStocksOutput(
        sector="Technology", market="US",
        stocks=[StockPickOutput(
            symbol="AAPL", company_name="Apple Inc.",
            current_price=175.0, currency="USD",
            change_percent=5.0, recommendation_score=9.0,
            reasoning="Strong."
        )]
    ).model_dump_json()

    with patch("app.services.data_fetchers.fetch_sector_stocks_sync",
               return_value=prefetched) as mock_fetch, \
         patch("app.services.crew_runner.run_with_cancellation",
               new=AsyncMock(return_value=valid_output_json)) as mock_runner:
        result = await service._run_stock_crew_for_sector(
            sector_info, "US", "30d", rank=1
        )

    mock_fetch.assert_called_once_with("Technology", "US", "30d")
    mock_runner.assert_called_once()
    kwargs = mock_runner.call_args.kwargs
    assert kwargs["target_name"] == "stock_crew"
    assert kwargs["args"]["prefetched_stocks"] == prefetched
    assert result["sector"] == "Technology"
    assert result["top_stocks"][0]["symbol"] == "AAPL"


async def test_run_stock_crew_raises_when_prefetch_empty(service):
    """Empty prefetched data must raise CrewExecutionError — never call the runner."""
    sector_info = SectorInfo(
        name="NotReal", performance_pct=0.0,
        trend="Up", momentum="Low", drivers=""
    )
    with patch("app.services.data_fetchers.fetch_sector_stocks_sync",
               return_value=[]), \
         patch("app.services.crew_runner.run_with_cancellation",
               new=AsyncMock()) as mock_runner:
        with pytest.raises(CrewExecutionError, match="No prefetched stock data"):
            await service._run_stock_crew_for_sector(sector_info, "US", "30d", rank=1)
    mock_runner.assert_not_called()


async def test_run_fund_crew_for_sector_uses_prefetch_and_runner(service):
    sector_info = SectorInfo(
        name="Technology", performance_pct=12.5,
        trend="Up", momentum="High", drivers="AI"
    )
    prefetched = [{"symbol": "XLK", "name": "Tech SPDR", "price": 195.0}]

    valid_output_json = SectorFundsOutput(
        sector="Technology", market="US",
        funds=[FundPickOutput(
            symbol="XLK", name="Tech SPDR",
            current_nav=195.0, currency="USD",
            change_percent=3.2, recommendation_score=8.5,
            reasoning="Top ETF."
        )]
    ).model_dump_json()

    with patch("app.services.data_fetchers.fetch_sector_etfs_sync",
               return_value=prefetched) as mock_fetch, \
         patch("app.services.crew_runner.run_with_cancellation",
               new=AsyncMock(return_value=valid_output_json)) as mock_runner:
        result = await service._run_fund_crew_for_sector(
            sector_info, "US", "30d", rank=1
        )

    mock_fetch.assert_called_once_with("Technology", "US", "30d")
    mock_runner.assert_called_once()
    assert mock_runner.call_args.kwargs["target_name"] == "fund_crew"
    assert result["top_funds"][0]["symbol"] == "XLK"
```

- [ ] **Step 3: Run the updated suite**

Run: `python -m pytest tests/test_recommendations_service.py -v`
Expected: all remaining + new tests pass (~10–12 total).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_recommendations_service.py
git commit -m "test(backend): update recommendations tests for prefetch architecture"
```

### Task 7.3: Add a chat service prefetch test

**Files:**
- Modify: `backend/tests/test_chat_service.py`

- [ ] **Step 1: Read the current file**

Run: `python -m pytest tests/test_chat_service.py -v --collect-only` to see what's there.

- [ ] **Step 2: Add a new test**

Append to `backend/tests/test_chat_service.py`:

```python
# ---------------------------------------------------------------------------
# Prefetch architecture integration
# ---------------------------------------------------------------------------

async def test_chat_service_prefetches_snapshot_and_calls_runner():
    """execute_chat_query must fetch snapshot, optionally news, then call runner."""
    from unittest.mock import patch, AsyncMock
    from app.services.chat_service import ChatService
    from app.crew.output_models import ChatAnswerOutput
    from app.models.requests import Source

    svc = ChatService(job_store=None)
    snapshot = {"symbol": "AAPL", "price": 175.0}
    news = [{"title": "Earnings", "publisher": "Reuters",
             "link": "http://x", "date": "2026-04-10"}]
    answer = ChatAnswerOutput(
        response="AAPL is trading at $175 with strong fundamentals.",
        sources=[Source(title="Earnings", url="http://x", date="2026-04-10")],
        agent_reasoning="Read snapshot and news.",
    )

    with patch("app.services.chat_service.classify_intent",
               new=AsyncMock(return_value={"needs_news": True, "needs_metrics": True,
                                            "needs_analysis": False, "needs_comparison": False})), \
         patch("app.services.chat_service.fetch_stock_snapshot_sync",
               return_value=snapshot) as mock_snap, \
         patch("app.services.chat_service.fetch_stock_news_sync",
               return_value=news) as mock_news, \
         patch("app.services.chat_service.run_with_cancellation",
               new=AsyncMock(return_value=answer.model_dump_json())) as mock_runner:
        result = await svc.execute_chat_query("How is AAPL?", "AAPL", "US")

    mock_snap.assert_called_once()
    mock_news.assert_called_once()
    mock_runner.assert_called_once()
    kwargs = mock_runner.call_args.kwargs
    assert kwargs["target_name"] == "chat_crew"
    assert kwargs["args"]["prefetched_snapshot"] == snapshot
    assert kwargs["args"]["prefetched_news"] == news
    assert "AAPL is trading" in result["response"]


async def test_chat_service_skips_news_when_intent_says_no():
    from unittest.mock import patch, AsyncMock
    from app.services.chat_service import ChatService
    from app.crew.output_models import ChatAnswerOutput

    svc = ChatService(job_store=None)
    answer = ChatAnswerOutput(response="ok", sources=[], agent_reasoning="no news needed")

    with patch("app.services.chat_service.classify_intent",
               new=AsyncMock(return_value={"needs_news": False, "needs_metrics": True,
                                            "needs_analysis": False, "needs_comparison": False})), \
         patch("app.services.chat_service.fetch_stock_snapshot_sync",
               return_value={"symbol": "AAPL"}), \
         patch("app.services.chat_service.fetch_stock_news_sync",
               return_value=[]) as mock_news, \
         patch("app.services.chat_service.run_with_cancellation",
               new=AsyncMock(return_value=answer.model_dump_json())):
        await svc.execute_chat_query("Price of AAPL?", "AAPL", "US")

    mock_news.assert_not_called()
```

- [ ] **Step 3: Run the tests**

Run: `python -m pytest tests/test_chat_service.py -v`
Expected: all pass (existing + 2 new).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_chat_service.py
git commit -m "test(backend): chat service prefetch + runner integration tests"
```

### Task 7.4: Run the full unit-test suite

- [ ] **Step 1: Run everything**

Run:
```bash
python -m pytest tests/test_job_store.py tests/test_output_models.py \
  tests/test_crew_service.py tests/test_chat_service.py \
  tests/test_recommendations_service.py tests/test_crew_runner.py \
  tests/test_data_fetchers.py -v
```
Expected: all tests pass. If something fails, read the failure, trace it back to the task that introduced the symbol, and fix before proceeding.

- [ ] **Step 2: If all green, commit any last fixups**

```bash
git status
# If there are straggler edits, commit them with a clear message.
```

---

## Phase 8 — Manual Smoke Tests

Unit tests cover the wiring; these smoke tests verify the real LLM + real yfinance pipeline end-to-end. **Do not skip them** — Bug 1/2 were only visible under real load.

### Task 8.1: Start the backend and ping health

- [ ] **Step 1: Start uvicorn**

```bash
cd backend
source .venv/Scripts/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: In another terminal, curl the health endpoint**

```bash
curl http://localhost:8000/health
```
Expected: `{"status": "ok", ...}`

### Task 8.2: Chat smoke test

- [ ] **Step 1: POST a chat query**

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"How is AAPL doing this month?","stock_symbol":"AAPL","market":"US"}'
```

Expected: a JSON response with `response`, `sources`, `agent_reasoning`, `stock_symbol`, `timestamp`. The `response` string should cite a specific price from the snapshot. Round-trip time should be **< 30 seconds**. Check `backend/logs/<today>.tx` — there should be NO Pydantic ValidationError, NO `'NoneType' object is not subscriptable`, and the crew should complete cleanly.

### Task 8.3: Stock recommendations smoke test

- [ ] **Step 1: POST a recommendation request**

```bash
curl -X POST http://localhost:8000/api/v1/stocks/recommendations \
  -H "Content-Type: application/json" \
  -d '{"market":"US","timeframe":"30d"}'
```
Expected: `{"job_id": "..."}`. Copy the job_id.

- [ ] **Step 2: Poll the job**

```bash
JOB_ID=<paste-here>
for i in 1 2 3 4 5 6 7 8 9 10; do
  curl -s http://localhost:8000/api/v1/stocks/recommendations/$JOB_ID | jq '.status, .message'
  sleep 5
done
```
Expected: `processing` → `completed` within ~60–120 seconds total (3 sectors × ~20s each). The final JSON should contain `top_sectors` with real stock picks. No ValidationError in the logs.

- [ ] **Step 3: Repeat for India market**

```bash
curl -X POST http://localhost:8000/api/v1/stocks/recommendations \
  -H "Content-Type: application/json" \
  -d '{"market":"IN","timeframe":"30d"}'
```
Poll the same way. Verify no Nifty sector throws a ValidationError.

### Task 8.4: Fund recommendations smoke test

- [ ] **Step 1: POST a fund recommendation request**

```bash
curl -X POST http://localhost:8000/api/v1/funds/recommendations \
  -H "Content-Type: application/json" \
  -d '{"market":"ALL","timeframe":"30d"}'
```
- [ ] **Step 2: Poll until completed**

Same polling loop as above. Expected `top_sectors` with `top_funds` containing XLK/XLF/etc. for US and Nifty indices for IN.

### Task 8.5: Cancellation smoke test (Bug 3 specifically)

- [ ] **Step 1: Temporarily lower `CREW_TIMEOUT_SECONDS` to 5**

Edit `backend/.env` and add:
```
CREW_TIMEOUT_SECONDS=5
```
Restart uvicorn. (5s is shorter than a real crew LLM turn, so the subprocess will be terminated mid-flight.)

- [ ] **Step 2: Trigger a chat query**

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Tell me about AAPL","stock_symbol":"AAPL","market":"US"}'
```
Expected: a 5xx response with "timed out" within ~7 seconds. **Crucial:** check the logs — there should be a `crew_runner: timeout on pid=... terminating` line followed by the request cleanup. There must be NO subsequent `Working Agent:` log lines after the timeout fires. This proves Bug 3 is fixed.

- [ ] **Step 3: Restore the timeout**

Remove or reset `CREW_TIMEOUT_SECONDS=5` from `.env`. Restart uvicorn.

### Task 8.6: Final log scan

- [ ] **Step 1: Search today's log file for red flags**

Search for each of these strings in `backend/logs/<today>.tx`. All should return 0 matches:
- `ValidationError`
- `'NoneType' object is not subscriptable`
- `No structured output`

If any match appears, open it, trace it to the crew/task involved, and fix before calling the refactor done.

---

## Phase 9 — Cleanup

### Task 9.1: Delete dead tool code

Now that no agent calls tools, the tool modules can be trimmed. **Do NOT delete `SectorPerformanceTool`, `US_SECTOR_ETFS`, `INDIA_SECTOR_INDICES`, `SectorStocksMapperTool`** — `recommendations_service.py` and `data_fetchers.py` still import them (the internal helpers, not as CrewAI tools).

- [ ] **Step 1: Check whether `PortfolioDataTool` and `YFinanceDataTool` are still referenced**

Run:
```bash
grep -rn "PortfolioDataTool\|YFinanceDataTool\|WebSearchTool\|NewsAPITool\|SentimentAnalysisTool" backend/app
```

- [ ] **Step 2: If only `agents.py` references them (via the remaining `market_researcher`), leave them**

Otherwise delete the unused tool classes from `backend/app/crew/tools/financial_data.py` and `backend/app/crew/tools/market_research.py` to avoid confusion.

- [ ] **Step 3: Commit cleanup if any**

```bash
git add backend/app/crew/tools/
git commit -m "chore(backend): remove unused tool classes after prefetch refactor"
```

### Task 9.2: Update `backend/CLAUDE.md`

- [ ] **Step 1: Revise the `Architecture` and `Key Patterns` sections**

In `backend/CLAUDE.md`, update the Key Patterns block to reflect prefetch:

Replace:
```
**Structured crew output:**
Tasks use `output_pydantic=<Model>` so agents return validated Pydantic objects. Access via `result.pydantic` (never `str(result)`).
```

With:
```
**Pre-fetch architecture:**
All deterministic financial data is fetched in Python (see `app/services/data_fetchers.py`)
and passed into task descriptions as JSON. Agents have NO tools and `max_iter=2` — they only
reason and emit structured JSON via `output_pydantic`.

**Cancellable crew execution:**
Every crew kickoff runs inside a child process spawned via `app/services/crew_runner.run_with_cancellation`.
On timeout the subprocess is terminated (no ghost threads). Target functions live as top-level
`_run_*_crew_inner` in `crew_runner.py` so they are picklable under the `spawn` multiprocessing context.
```

- [ ] **Step 2: Commit doc update**

```bash
git add backend/CLAUDE.md
git commit -m "docs(backend): document prefetch + cancellable-crew architecture"
```

### Task 9.3: Final test run

- [ ] **Step 1: Run the full unit suite one more time**

```bash
python -m pytest tests/ -v --ignore=tests/test_chat.py --ignore=tests/test_stocks.py --ignore=tests/test_funds.py
```
Expected: all pass.

- [ ] **Step 2: Check git log shows clean commit history**

```bash
git log --oneline feature/nextjs-frontend ^master | head -30
```
Expected: commits from Phases 1–9 in order.

---

## Acceptance Criteria

The refactor is complete when ALL of these are true:

1. `python -m pytest tests/ -v --ignore=tests/test_chat.py --ignore=tests/test_stocks.py --ignore=tests/test_funds.py` passes.
2. Phase 8 smoke tests all succeed:
   - Chat returns a valid answer in under 30s for US and IN stocks.
   - Stock and fund recommendations return `completed` status within 120s for US, IN, and ALL markets.
   - Forced-timeout test shows the subprocess is terminated and no ghost-crew log lines appear after timeout.
3. `backend/logs/<today>.tx` after smoke testing contains zero `ValidationError`, zero `NoneType` subscript errors, zero `No structured output` warnings.
4. `git grep "reflect_on_stock_picks\|reflect_on_fund_picks\|_run_crew_with_timeout" backend/` returns nothing.
5. `git grep "tools=\[" backend/app/crew/agents.py` shows only `tools=[]` for `financial_data_analyst` and `investment_advisor` (market_researcher/sector_performance_analyst may still have tools — they're unused by flows now but kept for reference).
6. `backend/CLAUDE.md` documents the prefetch and cancellable-crew architecture.

---

## Rollback

If something goes catastrophically wrong mid-implementation:

```bash
git log --oneline -20                     # find the commit BEFORE phase 1
git checkout <pre-phase-1-sha> -- backend
git status                                # review what's being reverted
git commit -m "revert: roll back prefetch refactor"
```

All commits in this plan are self-contained per phase, so partial rollback by cherry-picking specific reverts is also feasible.
