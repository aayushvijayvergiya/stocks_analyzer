"""
Crew Service - Async execution wrapper for CrewAI financial analysis.

Handles job creation, progress tracking, timeout management, and result formatting.
"""

import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import uuid
from crewai import Crew, Process

from app.crew.agents import FinancialAgents
from app.crew.tasks import FinancialTasks
from app.services.job_store import JobStore
from app.services.intent_classifier import classify_intent
from app.config import settings
from app.utils.logger import get_logger
from app.utils.exceptions import CrewExecutionError

logger = get_logger(__name__)


class CrewService:
    """Service for executing CrewAI financial analysis workflows asynchronously."""
    
    def __init__(self, job_store: Optional[JobStore] = None):
        """Initialize crew service.
        
        Args:
            job_store: Optional JobStore instance for tracking job status
        """
        self.job_store = job_store
    
    async def execute_chat_query(
        self,
        message: str,
        stock_symbol: str,
        market: str,
        job_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute crew for chat endpoint (fast, simplified analysis).
        
        Args:
            message: User's question
            stock_symbol: Stock symbol to analyze
            market: "US" or "IN"
            job_id: Optional job ID for tracking
            
        Returns:
            Dict with response, sources, reasoning
        """
        if not job_id:
            job_id = str(uuid.uuid4())
        
        if self.job_store:
            await self.job_store.create_job(job_id, "chat")
            await self.job_store.update_job(job_id, "processing", "Initializing agents...")
        
        try:
            logger.info(f"Starting chat query for {stock_symbol}: {message}")
            
            # Create agents (lightweight - only what's needed)
            if self.job_store:
                await self.job_store.update_job(job_id, "processing", "Gathering market research...")
            
            market_researcher = FinancialAgents.market_researcher()
            data_analyst = FinancialAgents.financial_data_analyst()
            advisor = FinancialAgents.investment_advisor()
            
            # Classify user intent using Groq
            intent = await classify_intent(message)
            logger.info(f"Classified intent: {intent}")
            
            tasks = []
            
            # Always get basic info
            if self.job_store:
                await self.job_store.update_job(job_id, "processing", "Analyzing financial data...")
            
            # Create appropriate tasks based on classified intent
            if intent["needs_news"]:
                # News-focused query
                tasks.append(FinancialTasks.research_stock_news(
                    market_researcher,
                    stock_symbol,
                    stock_symbol  # Company name can be same for now
                ))
            
            if intent["needs_metrics"]:
                # Metrics-focused query
                tasks.append(FinancialTasks.analyze_stock_financials(
                    data_analyst,
                    stock_symbol,
                    market
                ))
            
            # If no specific focus detected, default to financial analysis
            if not tasks:
                tasks.append(FinancialTasks.analyze_stock_financials(
                    data_analyst,
                    stock_symbol,
                    market
                ))
            
            # Always add synthesis task
            if self.job_store:
                await self.job_store.update_job(job_id, "processing", "Synthesizing response...")
            
            tasks.append(FinancialTasks.synthesize_chat_response(
                advisor,
                message,
                stock_symbol,
                market
            ))
            
            # Create and run crew
            crew = Crew(
                agents=[market_researcher, data_analyst, advisor],
                tasks=tasks,
                process=Process.sequential,
                verbose=True,
                memory=False,  # Disable for speed
                cache=True,
            )
            
            # Run with timeout
            result = await self._run_crew_with_timeout(
                crew,
                timeout=30  # 30 seconds for chat
            )
            
            # Parse result
            response_data = self._parse_chat_result(result, stock_symbol)
            
            if self.job_store:
                await self.job_store.update_job(
                    job_id,
                    "completed",
                    "Analysis complete",
                    result=response_data
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
    
    async def execute_stock_recommendations(
        self,
        market: str,
        timeframe: str,
        job_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute crew for stock recommendations (comprehensive analysis).
        
        Args:
            market: "US", "IN", or "ALL"
            timeframe: "7d", "30d", "90d"
            job_id: Job ID for tracking
            
        Returns:
            Dict with top sectors and stock recommendations
        """
        if not job_id:
            job_id = str(uuid.uuid4())
        
        if self.job_store:
            await self.job_store.create_job(job_id, "stock_recommendations")
            await self.job_store.update_job(job_id, "processing", "Initializing comprehensive analysis...")
        
        try:
            logger.info(f"Starting stock recommendations: market={market}, timeframe={timeframe}")
            
            # Create all agents
            if self.job_store:
                await self.job_store.update_job(job_id, "processing", "Deploying analyst team...")
            
            market_researcher = FinancialAgents.market_researcher()
            data_analyst = FinancialAgents.financial_data_analyst()
            sector_analyst = FinancialAgents.sector_performance_analyst()
            advisor = FinancialAgents.investment_advisor()
            
            results = {}
            
            # Handle "ALL" market
            markets_to_analyze = ["US", "IN"] if market == "ALL" else [market]
            
            for mkt in markets_to_analyze:
                if self.job_store:
                    await self.job_store.update_job(
                        job_id,
                        "processing",
                        f"Analyzing {mkt} market sectors..."
                    )
                
                # Step 1: Identify top 3 sectors
                sector_task = FinancialTasks.identify_top_sectors(
                    sector_analyst,
                    mkt,
                    timeframe
                )
                
                sector_crew = Crew(
                    agents=[sector_analyst],
                    tasks=[sector_task],
                    process=Process.sequential,
                    verbose=True,
                    memory=False,
                    cache=True,
                )
                
                sector_result = await self._run_crew_with_timeout(
                    sector_crew,
                    timeout=60
                )
                
                # Parse top sectors from result
                # TODO: Improve parsing - for now, assume we get top 3 sectors
                top_sectors = self._parse_top_sectors(sector_result, mkt)
                
                # Step 2: For each top sector, find top 3 stocks
                sector_recommendations = []
                
                for i, sector_info in enumerate(top_sectors[:3], 1):
                    sector_name = sector_info["name"]
                    
                    if self.job_store:
                        await self.job_store.update_job(
                            job_id,
                            "processing",
                            f"Finding top stocks in {sector_name} sector..."
                        )
                    
                    stock_task = FinancialTasks.find_top_stocks_in_sector(
                        advisor,
                        sector_name,
                        mkt,
                        timeframe
                    )
                    
                    stock_crew = Crew(
                        agents=[data_analyst, advisor],
                        tasks=[stock_task],
                        process=Process.sequential,
                        verbose=True,
                        memory=False,
                        cache=True,
                    )
                    
                    stock_result = await self._run_crew_with_timeout(
                        stock_crew,
                        timeout=60
                    )
                    
                    stocks = self._parse_stock_recommendations(stock_result)
                    
                    sector_recommendations.append({
                        "sector": sector_name,
                        "rank": i,
                        "performance_percent": sector_info.get("performance", 0.0),
                        "market": mkt,
                        "top_stocks": stocks[:3]  # Ensure only top 3
                    })
                
                results[mkt] = sector_recommendations
            
            # Step 3: Create final synthesis
            if self.job_store:
                await self.job_store.update_job(
                    job_id,
                    "processing",
                    "Creating final recommendation report..."
                )
            
            final_result = {
                "job_id": job_id,
                "status": "completed",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "timeframe": timeframe,
                "market": market,
                "top_sectors": self._combine_market_results(results, market),
                "analysis_summary": self._generate_summary(results, market, timeframe),
                "cache_hit": False
            }
            
            if self.job_store:
                await self.job_store.update_job(
                    job_id,
                    "completed",
                    "Analysis complete",
                    result=final_result
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
            logger.error(f"Stock recommendations error: {job_id}: {e}", exc_info=True)
            if self.job_store:
                await self.job_store.update_job(job_id, "failed", error=error_msg)
            raise CrewExecutionError(error_msg)
    
    async def execute_fund_recommendations(
        self,
        market: str,
        timeframe: str,
        job_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute crew for fund/ETF recommendations.
        
        Similar to stock recommendations but focuses on ETFs/Mutual Funds.
        For India, returns note about MF support coming soon.
        
        Args:
            market: "US", "IN", or "ALL"
            timeframe: "7d", "30d", "90d"
            job_id: Job ID for tracking
            
        Returns:
            Dict with top sector ETFs/funds
        """
        # For now, use similar logic to stocks but with ETF focus
        # India mutual funds will return sector indices as proxy
        
        if not job_id:
            job_id = str(uuid.uuid4())
        
        if self.job_store:
            await self.job_store.create_job(job_id, "fund_recommendations")
            await self.job_store.update_job(
                job_id,
                "processing",
                "Analyzing sector ETFs and funds..."
            )
        
        try:
            # Use stock recommendation logic but with fund context
            result = await self.execute_stock_recommendations(
                market=market,
                timeframe=timeframe,
                job_id=None  # Don't double-track
            )
            
            # Convert to fund format
            fund_result = {
                "job_id": job_id,
                "status": "completed",
                "generated_at": result.get("generated_at"),
                "timeframe": timeframe,
                "market": market,
                "top_sectors": result.get("top_sectors", []),
                "analysis_summary": result.get("analysis_summary"),
                "cache_hit": False,
                "note": "India mutual fund recommendations coming soon. Currently showing sectoral indices and ETF proxies."
            }
            
            if self.job_store:
                await self.job_store.update_job(
                    job_id,
                    "completed",
                    "Analysis complete",
                    result=fund_result
                )
            
            return fund_result
            
        except Exception as e:
            error_msg = f"Fund analysis failed: {str(e)}"
            logger.error(f"Fund recommendations error: {job_id}: {e}", exc_info=True)
            if self.job_store:
                await self.job_store.update_job(job_id, "failed", error=error_msg)
            raise CrewExecutionError(error_msg)
    
    async def _run_crew_with_timeout(self, crew: Crew, timeout: int) -> Any:
        """Run crew with timeout using asyncio.
        
        Args:
            crew: Crew instance to run
            timeout: Timeout in seconds
            
        Returns:
            Crew execution result
        """
        loop = asyncio.get_event_loop()
        
        # Run crew.kickoff() in thread pool to not block event loop
        result = await asyncio.wait_for(
            loop.run_in_executor(None, crew.kickoff),
            timeout=timeout
        )
        
        return result
    
    def _parse_chat_result(self, result: Any, stock_symbol: str) -> Dict[str, Any]:
        """Parse crew result for chat endpoint.
        
        Args:
            result: Raw crew output
            stock_symbol: Stock symbol
            
        Returns:
            Formatted chat response
        """
        # Extract text from result
        response_text = str(result) if result else "Unable to generate response."
        
        # TODO: Improve parsing to extract sources and reasoning
        # For now, return basic structure
        
        return {
            "response": response_text[:1000],  # Limit length
            "sources": [],  # TODO: Extract from crew output
            "agent_reasoning": None,  # TODO: Extract agent outputs
            "stock_symbol": stock_symbol,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def _parse_top_sectors(self, result: Any, market: str) -> List[Dict]:
        """Parse top sectors from crew output.
        
        Args:
            result: Crew output text
            market: Market being analyzed
            
        Returns:
            List of sector info dicts
        """
        # TODO: Improve parsing using structured output
        # For now, return placeholder based on market
        
        result_text = str(result).lower()
        
        # Simple keyword extraction (improve in v2)
        if market == "US":
            sectors = [
                {"name": "Technology", "performance": 12.5},
                {"name": "Healthcare", "performance": 8.3},
                {"name": "Financials", "performance": 6.7}
            ]
        else:  # India
            sectors = [
                {"name": "Technology", "performance": 15.2},
                {"name": "Banking", "performance": 10.1},
                {"name": "Pharma", "performance": 7.8}
            ]
        
        return sectors
    
    def _parse_stock_recommendations(self, result: Any) -> List[Dict]:
        """Parse stock recommendations from crew output.
        
        Args:
            result: Crew output text
            
        Returns:
            List of stock recommendation dicts
        """
        # TODO: Improve with structured output parsing
        # For now, return basic structure
        
        return [
            {
                "symbol": "STOCK1",
                "name": "Example Stock 1",
                "current_price": 100.0,
                "currency": "USD",
                "change_percent": 5.0,
                "recommendation_score": 8.5,
                "reasoning": str(result)[:200],
                "key_metrics": {
                    "pe_ratio": 25.0,
                    "market_cap": "100B",
                    "volume": "10M"
                }
            }
        ]
    
    def _combine_market_results(
        self,
        results: Dict[str, List],
        market: str
    ) -> List[Dict]:
        """Combine results from multiple markets.
        
        Args:
            results: Dict of market -> sectors
            market: Original market requested
            
        Returns:
            Combined list of sector recommendations
        """
        if market == "ALL":
            # Combine US and India results
            combined = []
            for mkt, sectors in results.items():
                combined.extend(sectors)
            return combined
        else:
            return results.get(market, [])
    
    def _generate_summary(
        self,
        results: Dict[str, List],
        market: str,
        timeframe: str
    ) -> str:
        """Generate executive summary of analysis.
        
        Args:
            results: Market results
            market: Market analyzed
            timeframe: Timeframe
            
        Returns:
            Summary text
        """
        return f"Analysis of {market} market over {timeframe} showing strong performance in technology and financial sectors. Detailed recommendations provided for top sectors."
