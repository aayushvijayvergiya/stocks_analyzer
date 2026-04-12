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
    # Mock yf.download to return a DataFrame with a "Close" column
    mock_hist = pd.DataFrame({"Close": [170.0, 175.5]}, index=[0, 1])
    
    with patch("app.services.data_fetchers.yf.Ticker", return_value=_mock_ticker(fake_info)), \
         patch("app.services.data_fetchers.yf.download", return_value=mock_hist):
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
