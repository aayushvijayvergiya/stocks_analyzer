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
STOCK_TIMEOUT = 60
FUND_TIMEOUT = 60


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
            market_researcher = FinancialAgents.market_researcher()
            data_analyst = FinancialAgents.financial_data_analyst()
            sector_analyst = FinancialAgents.sector_performance_analyst()
            advisor = FinancialAgents.investment_advisor()

            results: Dict[str, List] = {}
            markets_to_analyze = ["US", "IN"] if market == "ALL" else [market]

            for mkt in markets_to_analyze:
                if self.job_store:
                    await self.job_store.update_job(
                        job_id, "processing", f"Analyzing {mkt} market sectors..."
                    )

                sector_task = FinancialTasks.identify_top_sectors(sector_analyst, mkt, timeframe)
                sector_crew = Crew(
                    agents=[sector_analyst],
                    tasks=[sector_task],
                    process=Process.sequential,
                    verbose=True, memory=False, cache=True,
                )
                sector_result = await self._run_crew_with_timeout(sector_crew, SECTOR_TIMEOUT)
                ranking: SectorRankingOutput = sector_result.pydantic
                top_sectors = ranking.sectors[:3]

                sector_recommendations = []
                for i, sector_info in enumerate(top_sectors, 1):
                    if self.job_store:
                        await self.job_store.update_job(
                            job_id, "processing",
                            f"Finding top stocks in {sector_info.name} sector..."
                        )

                    stock_task = FinancialTasks.find_top_stocks_in_sector(
                        advisor, sector_info.name, mkt, timeframe
                    )
                    stock_crew = Crew(
                        agents=[data_analyst, advisor],
                        tasks=[stock_task],
                        process=Process.sequential,
                        verbose=True, memory=False, cache=True,
                    )
                    stock_result = await self._run_crew_with_timeout(stock_crew, STOCK_TIMEOUT)
                    stocks_output: SectorStocksOutput = stock_result.pydantic

                    sector_recommendations.append({
                        "sector": sector_info.name,
                        "rank": i,
                        "performance_percent": sector_info.performance_pct,
                        "market": mkt,
                        "top_stocks": [s.model_dump() for s in stocks_output.stocks[:3]]
                    })

                results[mkt] = sector_recommendations

            if self.job_store:
                await self.job_store.update_job(
                    job_id, "processing", "Creating final recommendation report..."
                )

            combined: List = []
            for mkt_results in results.values():
                combined.extend(mkt_results)

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
            sector_analyst = FinancialAgents.sector_performance_analyst()
            data_analyst = FinancialAgents.financial_data_analyst()
            advisor = FinancialAgents.investment_advisor()

            results: Dict[str, List] = {}
            markets_to_analyze = ["US", "IN"] if market == "ALL" else [market]

            for mkt in markets_to_analyze:
                if self.job_store:
                    await self.job_store.update_job(
                        job_id, "processing", f"Analyzing {mkt} market sectors for ETFs..."
                    )

                sector_task = FinancialTasks.identify_top_sectors(sector_analyst, mkt, timeframe)
                sector_crew = Crew(
                    agents=[sector_analyst],
                    tasks=[sector_task],
                    process=Process.sequential,
                    verbose=True, memory=False, cache=True,
                )
                sector_result = await self._run_crew_with_timeout(sector_crew, SECTOR_TIMEOUT)
                ranking: SectorRankingOutput = sector_result.pydantic
                top_sectors = ranking.sectors[:3]

                sector_fund_recommendations = []
                for i, sector_info in enumerate(top_sectors, 1):
                    if self.job_store:
                        await self.job_store.update_job(
                            job_id, "processing",
                            f"Finding top ETFs in {sector_info.name} sector..."
                        )

                    etf_task = FinancialTasks.identify_top_etfs_in_sector(
                        advisor, sector_info.name, mkt, timeframe
                    )
                    etf_crew = Crew(
                        agents=[data_analyst, advisor],
                        tasks=[etf_task],
                        process=Process.sequential,
                        verbose=True, memory=False, cache=True,
                    )
                    etf_result = await self._run_crew_with_timeout(etf_crew, FUND_TIMEOUT)
                    funds_output: SectorFundsOutput = etf_result.pydantic

                    sector_fund_recommendations.append({
                        "sector": sector_info.name,
                        "rank": i,
                        "performance_percent": sector_info.performance_pct,
                        "market": mkt,
                        "top_funds": [f.model_dump() for f in funds_output.funds[:3]]
                    })

                results[mkt] = sector_fund_recommendations

            combined: List = []
            for mkt_results in results.values():
                combined.extend(mkt_results)

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

    async def _run_crew_with_timeout(self, crew: Crew, timeout: int):
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, crew.kickoff),
            timeout=timeout
        )
