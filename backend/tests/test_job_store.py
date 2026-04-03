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


async def test_create_job_sets_ttl(job_store, mock_redis):
    await job_store.create_job("job-1", "chat")
    mock_redis.set.assert_called_once()
    call_kwargs = mock_redis.set.call_args.kwargs
    assert call_kwargs.get("ex") == 3600


async def test_get_job_returns_none_for_missing_job(job_store, mock_redis):
    mock_redis.get.return_value = None
    result = await job_store.get_job("nonexistent-job")
    assert result is None


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


async def test_update_job_with_explicit_result_writes_result(job_store, mock_redis):
    """Passing result=dict explicitly must write it to Redis."""
    existing = {
        "job_id": "job-1", "type": "chat", "status": "processing",
        "progress": "Working...", "created_at": "2026-03-29T00:00:00+00:00",
        "completed_at": None, "result": None, "error": None
    }
    mock_redis.get.return_value = json.dumps(existing)

    await job_store.update_job("job-1", "completed", result={"answer": 42})

    saved = json.loads(mock_redis.set.call_args[0][1])
    assert saved["result"] == {"answer": 42}
