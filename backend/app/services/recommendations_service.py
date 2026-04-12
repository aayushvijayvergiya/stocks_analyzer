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


class RecommendationsService:
    """Executes stock and fund recommendation crews with structured output parsing."""

    def __init__(self, job_store: Optional[JobStore] = None):
        self.job_store = job_store

    async def execute_stock_recommendations(
        self,
        market: str,
        timeframe: str,
        job_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute stock recommendation crews.

        Flow per market: identify top sectors → for each sector, find top 3 stocks.

        Args:
            market: "US", "IN", or "ALL"
            timeframe: "7d", "30d", "90d"
            job_id: Job ID for tracking

        Returns:
            Dict with job_id, status, top_sectors (real AI-generated data)
        """
        if not job_id:
            job_id = str(uuid.uuid4())

        if self.job_store:
            await self.job_store.create_job(job_id, "stock_recommendations")
            await self.job_store.update_job(job_id, "processing", "Initializing comprehensive analysis...")

        try:
            markets_to_analyze = ["US", "IN"] if market == "ALL" else [market]

            if self.job_store:
                await self.job_store.update_job(
                    job_id, "processing", "Analyzing market sectors in parallel..."
                )

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

            if self.job_store:
                await self.job_store.update_job(
                    job_id, "processing", "Creating final recommendation report..."
                )

            final_result = {
                "job_id": job_id,
                "status": "completed",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "timeframe": timeframe,
                "market": market,
                "top_sectors": combined,
                "analysis_summary": (
                    f"Analysis of {market} market over {timeframe} based on real-time "
                    "sector performance data and AI-driven stock selection."
                ),
                "cache_hit": False
            }

            if self.job_store:
                await self.job_store.update_job(
                    job_id, "completed", "Analysis complete", result=final_result
                )

            logger.info(f"Stock recommendations completed: {job_id}")
            return final_result

        except asyncio.TimeoutError:
            error_msg = "Analysis timed out. The market analysis is taking longer than expected."
            logger.error(f"Stock recommendations timeout: {job_id}")
            if self.job_store:
                await self.job_store.update_job(job_id, "failed", error=error_msg)
            raise CrewExecutionError(error_msg)

        except Exception as e:
            error_msg = f"Recommendation analysis failed: {str(e)}"
            logger.error(f"Stock recommendations error {job_id}: {e}", exc_info=True)
            if self.job_store:
                await self.job_store.update_job(job_id, "failed", error=error_msg)
            raise CrewExecutionError(error_msg)

    async def execute_fund_recommendations(
        self,
        market: str,
        timeframe: str,
        job_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute fund/ETF recommendation crews.

        Fully separate from stock recommendations — uses identify_top_etfs_in_sector task
        which targets ETF symbols (XLK, XLF for US; Nifty indices for India).

        Args:
            market: "US", "IN", or "ALL"
            timeframe: "7d", "30d", "90d"
            job_id: Job ID for tracking

        Returns:
            Dict with job_id, status, top_sectors containing real ETF data
        """
        if not job_id:
            job_id = str(uuid.uuid4())

        if self.job_store:
            await self.job_store.create_job(job_id, "fund_recommendations")
            await self.job_store.update_job(
                job_id, "processing", "Analyzing sector ETFs and funds..."
            )

        try:
            markets_to_analyze = ["US", "IN"] if market == "ALL" else [market]

            if self.job_store:
                await self.job_store.update_job(
                    job_id, "processing", "Analyzing sector ETFs in parallel..."
                )

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

            final_result = {
                "job_id": job_id,
                "status": "completed",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "timeframe": timeframe,
                "market": market,
                "top_sectors": combined,
                "analysis_summary": (
                    f"ETF/Fund analysis of {market} market over {timeframe}."
                ),
                "cache_hit": False
            }

            if self.job_store:
                await self.job_store.update_job(
                    job_id, "completed", "Analysis complete", result=final_result
                )

            logger.info(f"Fund recommendations completed: {job_id}")
            return final_result

        except asyncio.TimeoutError:
            error_msg = "Fund analysis timed out."
            logger.error(f"Fund recommendations timeout: {job_id}")
            if self.job_store:
                await self.job_store.update_job(job_id, "failed", error=error_msg)
            raise CrewExecutionError(error_msg)

        except Exception as e:
            error_msg = f"Fund analysis failed: {str(e)}"
            logger.error(f"Fund recommendations error {job_id}: {e}", exc_info=True)
            if self.job_store:
                await self.job_store.update_job(job_id, "failed", error=error_msg)
            raise CrewExecutionError(error_msg)

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

        loop = asyncio.get_running_loop()
        prefetched = await loop.run_in_executor(
            None, fetch_sector_stocks_sync, sector_info.name, market, timeframe
        )
        if not prefetched:
            # yfinance returned no data for this sector — log and propagate so
            # the caller's per-sector try/except can skip it and continue.
            logger.warning(f"No stock data available for {sector_info.name} ({market})")
            raise ValueError(f"No stock data available for {sector_info.name} ({market})")

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
            "market": market,
            "top_stocks": [s.model_dump() for s in stocks_output.stocks[:3]],
        }

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

        loop = asyncio.get_running_loop()
        prefetched = await loop.run_in_executor(
            None, fetch_sector_etfs_sync, sector_info.name, market, timeframe
        )
        if not prefetched:
            logger.warning(f"No ETF data available for {sector_info.name} ({market})")
            raise ValueError(f"No ETF data available for {sector_info.name} ({market})")

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

    async def _run_market_stock_analysis(
        self,
        market: str,
        timeframe: str,
        job_id: Optional[str],
    ) -> List[dict]:
        """Identify top sectors via direct yfinance fetch, then run per-sector stock crews."""
        if self.job_store:
            await self.job_store.update_job(
                job_id, "processing", f"Analyzing {market} market sectors..."
            )

        ranking = await self._get_top_sectors_direct(market, timeframe)
        top_sectors = ranking.sectors[:3]

        # Sectors run sequentially (not concurrently) to avoid saturating
        # the free-tier rate-limit window. Worst-case: ~3 × CREW_TIMEOUT_SECONDS.
        # Partial success is preserved — a failed sector is skipped, not fatal.
        successful = []
        for i, sector_info in enumerate(top_sectors, 1):
            if self.job_store:
                await self.job_store.update_job(
                    job_id, "processing",
                    f"Analyzing sector {i}/{len(top_sectors)}: {sector_info.name} ({market})..."
                )
            try:
                result = await self._run_stock_crew_for_sector(sector_info, market, timeframe, rank=i)
                successful.append(result)
            except Exception as e:
                logger.warning(f"Sector {i} stock analysis failed for {market}: {e}")

        if not successful:
            raise CrewExecutionError(f"All sector analyses failed for {market} market.")

        return successful

    async def _run_market_fund_analysis(
        self,
        market: str,
        timeframe: str,
        job_id: Optional[str],
    ) -> List[dict]:
        """Identify top sectors via direct yfinance fetch, then run per-sector fund crews."""
        if self.job_store:
            await self.job_store.update_job(
                job_id, "processing", f"Analyzing {market} market sectors for ETFs..."
            )

        ranking = await self._get_top_sectors_direct(market, timeframe)
        top_sectors = ranking.sectors[:3]

        # Sectors run sequentially — same rate-limit reasoning as stock analysis.
        successful = []
        for i, sector_info in enumerate(top_sectors, 1):
            if self.job_store:
                await self.job_store.update_job(
                    job_id, "processing",
                    f"Analyzing sector {i}/{len(top_sectors)}: {sector_info.name} ({market}) ETFs..."
                )
            try:
                result = await self._run_fund_crew_for_sector(sector_info, market, timeframe, rank=i)
                successful.append(result)
            except Exception as e:
                logger.warning(f"Sector {i} fund analysis failed for {market}: {e}")

        if not successful:
            raise CrewExecutionError(f"All fund sector analyses failed for {market} market.")

        return successful

    async def _get_top_sectors_direct(self, market: str, timeframe: str) -> SectorRankingOutput:
        """Fetch top sectors via yfinance directly — no LLM crew needed."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._fetch_sectors_sync, market, timeframe)

    def _fetch_sectors_sync(self, market: str, timeframe: str) -> SectorRankingOutput:
        """Synchronous sector fetch using SectorPerformanceTool internals."""
        sectors_map = US_SECTOR_ETFS if market == "US" else INDIA_SECTOR_INDICES
        tool = SectorPerformanceTool()
        sector_performance = []

        for sector_name, symbol in sectors_map.items():
            try:
                perf = tool._get_sector_performance(symbol, sector_name, timeframe)
                if perf:
                    sector_performance.append(perf)
            except Exception as e:
                logger.warning(f"Failed to fetch {sector_name} ({symbol}) for {market}: {e}")

        if not sector_performance:
            raise CrewExecutionError(f"No sector performance data available for {market} market.")

        sector_performance.sort(key=lambda x: x["performance_pct"], reverse=True)

        return SectorRankingOutput(sectors=[
            SectorInfo(
                name=s["name"],
                performance_pct=round(s["performance_pct"], 2),
                trend=s["trend"],
                momentum=s["momentum"],
                drivers=(
                    f"{s['name']} ({s['symbol']}): {s['performance_pct']:+.2f}% over {timeframe}. "
                    f"Trend: {s['trend']}, momentum {s['momentum'].lower()}. "
                    f"Volatility: {s['volatility']:.2f}%."
                ),
            )
            for s in sector_performance[:3]
        ])
