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
        # Handle single vs multi-column results from yf.download
        if n_symbols == 1:
            col = close
        else:
            col = close[symbol]
        
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
