"""
Recommendations Service — executes stock and fund recommendation crews.

Stock recommendations: sector identification crew → per-sector stock picking crew.
Fund recommendations: sector identification crew → per-sector ETF picking crew (separate from stocks).
"""

import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import uuid
from crewai import Crew, Process

from app.crew.agents import FinancialAgents
from app.crew.tasks import FinancialTasks
from app.crew.output_models import SectorRankingOutput, SectorStocksOutput, SectorFundsOutput
from app.services.job_store import JobStore
from app.utils.logger import get_logger
from app.utils.exceptions import CrewExecutionError

logger = get_logger(__name__)

SECTOR_TIMEOUT = 60
STOCK_TIMEOUT = 90   # increased to accommodate reflection task
FUND_TIMEOUT = 90    # increased to accommodate reflection task


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
        """Run a sequential stock picking + reflection crew for one sector.

        Creates its own agent instances so it is safe to run concurrently.
        """
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

    async def _run_fund_crew_for_sector(
        self,
        sector_info,
        market: str,
        timeframe: str,
        rank: int,
    ) -> dict:
        """Run a sequential fund picking + reflection crew for one sector.

        Creates its own agent instances so it is safe to run concurrently.
        """
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

    async def _run_market_stock_analysis(
        self,
        market: str,
        timeframe: str,
        job_id: Optional[str],
    ) -> List[dict]:
        """Identify top sectors then run per-sector stock crews in parallel for one market."""
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
                logger.warning(f"Sector {i + 1} stock analysis failed for {market}: {res}")
            else:
                successful.append(res)

        if not successful:
            raise CrewExecutionError(f"All sector analyses failed for {market} market.")

        return successful

    async def _run_market_fund_analysis(
        self,
        market: str,
        timeframe: str,
        job_id: Optional[str],
    ) -> List[dict]:
        """Identify top sectors then run per-sector fund crews in parallel for one market."""
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
                logger.warning(f"Sector {i + 1} fund analysis failed for {market}: {res}")
            else:
                successful.append(res)

        if not successful:
            raise CrewExecutionError(f"All fund sector analyses failed for {market} market.")

        return successful

    async def _run_crew_with_timeout(self, crew: Crew, timeout: int):
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, crew.kickoff),
            timeout=timeout
        )
