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
    # No CREW_RUNNER_TEST_TARGET override — this test spawns a real subprocess
    # to validate the dispatch map. Requires multiprocessing spawn support in CI.
    with pytest.raises(CrewExecutionError, match="Unknown target"):
        await run_with_cancellation(
            target_name="not_a_real_target",
            args={},
            timeout=10,
        )
