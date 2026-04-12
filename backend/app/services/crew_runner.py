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
from typing import Any

from app.utils.logger import get_logger
from app.utils.exceptions import CrewExecutionError

logger = get_logger(__name__)


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

    loop = asyncio.get_running_loop()

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
# These are called by _subprocess_entry.
# ---------------------------------------------------------------------------

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
