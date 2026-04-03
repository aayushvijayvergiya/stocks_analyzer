from crewai import Task
from typing import List
from datetime import datetime
from app.crew.output_models import (
    SectorRankingOutput,
    SectorStocksOutput,
    ChatAnswerOutput,
    SectorFundsOutput,
)

class FinancialTasks:
    """Factory class for creating financial analysis tasks."""
    
    @staticmethod
    def research_stock_news(agent, stock_symbol: str, company_name: str) -> Task:
        """Task: Research latest news and sentiment for a stock."""
        return Task(
            description=f"""Research the latest news and market sentiment for {company_name} ({stock_symbol}).
            
            Your objectives:
            1. Search for latest news articles (last 7 days) about {company_name}
            2. Gather information about recent events affecting the stock
            3. Analyze overall sentiment from headlines and articles
            4. Identify any major catalysts (earnings, product launches, regulatory issues)
            5. Note any analyst upgrades/downgrades
            
            Stock: {stock_symbol}
            Company: {company_name}
            Date: {datetime.now().strftime('%Y-%m-%d')}
            
            Use web search and news APIs to gather comprehensive information.
            Focus on credible sources (financial news sites, company press releases).
            """,
            expected_output=f"""A structured news and sentiment report containing:
            - Summary of top 5-7 most relevant recent news articles with titles and dates
            - Overall sentiment assessment (Positive/Negative/Neutral) with confidence level
            - Key catalysts or events affecting the stock
            - Any significant analyst opinions or ratings
            - Brief assessment of how news might impact stock price (bullish/bearish factors)
            
            Format the output clearly with sections and bullet points.""",
            agent=agent,
        )
    
    @staticmethod
    def analyze_stock_financials(agent, stock_symbol: str, market: str) -> Task:
        """Task: Analyze financial metrics and performance."""
        return Task(
            description=f"""Perform comprehensive quantitative analysis of {stock_symbol} in the {market} market.
            
            Your objectives:
            1. Fetch current price, volume, and market cap
            2. Calculate key financial ratios: P/E, EPS, ROE, Debt-to-Equity
            3. Analyze historical performance over last 30 days
            4. Compare metrics to sector average/benchmark
            5. Assess financial health and value proposition
            6. Identify any red flags or exceptional strengths
            
            Stock Symbol: {stock_symbol}
            Market: {market}
            Date: {datetime.now().strftime('%Y-%m-%d')}
            
            Use yfinance tools to fetch accurate real-time data.
            """,
            expected_output=f"""A detailed financial analysis report containing:
            - Current stock price and change (% and absolute)
            - Trading volume and liquidity assessment
            - Market capitalization
            - Key ratios: P/E, EPS, ROE, Debt/Equity, Dividend Yield
            - 30-day performance (% change, volatility)
            - Comparison to sector averages
            - Financial health score (0-10) with explanation
            - Value assessment (overvalued/fairly valued/undervalued)
            - Top 3 financial strengths and top 3 concerns
            
            Present numbers clearly with proper formatting.""",
            agent=agent,
        )
    
    @staticmethod
    def identify_top_sectors(agent, market: str, timeframe: str) -> Task:
        """Task: Identify and rank top performing sectors."""
        return Task(
            description=f"""Identify the top 3 performing sectors in the {market} market over the {timeframe} timeframe.
            
            Your objectives:
            1. Analyze performance of all major sectors
            2. Rank sectors by performance (% gain/loss)
            3. Identify momentum and trends in each sector
            4. Understand what's driving sector performance
            5. Select the top 3 performing sectors
            
            Market: {market}
            Timeframe: {timeframe}
            Date: {datetime.now().strftime('%Y-%m-%d')}
            
            Use sector performance tools to analyze ETFs (US) or indices (India).
            """,
            expected_output=f"""Return a JSON object matching this exact schema:
            {{
              "sectors": [
                {{
                  "name": "Technology",
                  "performance_pct": 12.5,
                  "trend": "Strong Uptrend",
                  "momentum": "Accelerating",
                  "drivers": "Brief explanation of what is driving this sector"
                }}
              ]
            }}
            Include exactly 3 sectors ranked by performance_pct descending.""",
            agent=agent,
            output_pydantic=SectorRankingOutput,
        )
    
    @staticmethod
    def find_top_stocks_in_sector(agent, sector: str, market: str, timeframe: str) -> Task:
        """Task: Find and rank top stocks within a sector."""
        return Task(
            description=f"""Find the top 3 stock picks in the {sector} sector for the {market} market.
            
            Your objectives:
            1. Get list of major stocks in the {sector} sector
            2. Fetch financial data and performance for each stock
            3. Analyze and compare stocks based on:
               - Financial health (P/E, ROE, debt levels)
               - Recent performance ({timeframe})
               - Growth prospects
               - Market position
            4. Rank and select the top 3 best opportunities
            5. Provide clear reasoning for each selection
            
            Sector: {sector}
            Market: {market}
            Timeframe: {timeframe}
            """,
            expected_output=f"""Return a JSON object matching this exact schema:
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
                  "reasoning": "3-4 sentence explanation",
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
            Include exactly 3 stocks. All numeric fields must be numbers, not strings.""",
            agent=agent,
            output_pydantic=SectorStocksOutput,
        )
    
    @staticmethod
    def synthesize_chat_response(agent, user_question: str, stock_symbol: str, market: str) -> Task:
        """Task: Answer user's question about a stock (for chat endpoint)."""
        return Task(
            description=f"""Answer the user's question about {stock_symbol} in a helpful, accurate, and concise way.
            
            User Question: "{user_question}"
            Stock Symbol: {stock_symbol}
            Market: {market}
            
            Your approach:
            1. Understand what the user is asking (price, news, recommendation, comparison, etc.)
            2. Gather relevant information:
               - If about price/metrics: fetch current data
               - If about news: search latest news
               - If about recommendation: provide balanced analysis
            3. Provide a conversational, helpful answer
            4. Cite sources where appropriate
            5. Keep it concise (200-400 words)
            
            This is a chat interaction - be helpful, clear, and conversational.
            """,
            expected_output=f"""Return a JSON object matching this exact schema:
            {{
              "response": "Your conversational answer here (200-400 words)",
              "sources": [
                {{
                  "title": "Article or data source title",
                  "url": "https://source-url.com",
                  "date": "YYYY-MM-DD"
                }}
              ],
              "agent_reasoning": "Brief explanation of how you arrived at this answer"
            }}
            The response must directly answer the user's question. sources can be an empty list if no external sources were used.""",
            agent=agent,
            output_pydantic=ChatAnswerOutput,
        )
    
    @staticmethod
    def create_comprehensive_recommendation(
        agent,
        market: str,
        timeframe: str,
        recommendation_type: str  # "stocks" or "funds"
    ) -> Task:
        """Task: Create final comprehensive recommendation report."""
        return Task(
            description=f"""Create a comprehensive {recommendation_type} recommendation report for {market} market.
            
            You will receive inputs from the team:
            - Market news and sentiment analysis
            - Top 3 performing sectors with performance data
            - Financial analysis of stocks in each sector
            
            Your objectives:
            1. Synthesize all inputs into a coherent report
            2. For each of the top 3 sectors, recommend the top 3 {recommendation_type}
            3. Provide clear, data-backed reasoning for each recommendation
            4. Include risk assessment
            5. Create an executive summary
            
            Market: {market}
            Timeframe: {timeframe}
            Type: {recommendation_type}
            Date: {datetime.now().strftime('%Y-%m-%d')}
            
            This is the final output that goes to the user - make it excellent.
            """,
            expected_output=f"""A comprehensive recommendation report structured as:
            
            EXECUTIVE SUMMARY:
            - Brief market overview (2-3 sentences)
            - Top sector highlights
            - Key themes driving recommendations
            
            TOP 3 SECTORS (ranked):
            For each sector:
              Sector Name and Performance
              Top 3 {recommendation_type} with:
                - Symbol, name, current price
                - Key metrics
                - Performance over {timeframe}
                - Recommendation score (0-10)
                - Clear reasoning (3-4 bullet points)
                - Risk considerations
            
            FINAL THOUGHTS:
            - Overall market outlook
            - Risk factors to monitor
            - Time horizon considerations
            
            Ensure all recommendations are actionable and data-driven.""",
            agent=agent,
        )

    @staticmethod
    def identify_top_etfs_in_sector(agent, sector: str, market: str, timeframe: str) -> Task:
        """Task: Find and rank top ETFs/funds within a sector."""
        US_SECTOR_ETFS = {
            "Technology": "XLK", "Healthcare": "XLV", "Financials": "XLF",
            "Consumer Discretionary": "XLY", "Industrials": "XLI", "Energy": "XLE",
            "Materials": "XLB", "Consumer Staples": "XLP", "Utilities": "XLU",
            "Real Estate": "XLRE", "Communication Services": "XLC"
        }
        INDIA_SECTOR_ETFS = {
            "Technology": "^CNXIT", "Banking": "^NSEBANK", "Pharma": "^CNXPHARMA",
            "Auto": "^CNXAUTO", "FMCG": "^CNXFMCG", "Metal": "^CNXMETAL",
            "Realty": "^CNXREALTY", "Financial Services": "^CNXFIN"
        }
        etf_map = US_SECTOR_ETFS if market == "US" else INDIA_SECTOR_ETFS
        primary_etf = etf_map.get(sector, "the sector ETF/index")
        currency = "USD" if market == "US" else "INR"

        return Task(
            description=f"""Find the top 3 ETF or fund picks in the {sector} sector for the {market} market.

            The primary ETF/index for this sector is: {primary_etf}

            Your objectives:
            1. Fetch current NAV/price and historical performance of {primary_etf} over {timeframe}
            2. Identify 2 additional ETFs or sector indices in the {sector} space for {market}
            3. For each ETF/fund fetch: current NAV, expense ratio (if available via yfinance info),
               AUM (if available), and % change over {timeframe}
            4. Rank them by performance and overall quality
            5. Provide clear reasoning for each

            Market: {market}
            Sector: {sector}
            Timeframe: {timeframe}
            Currency: {currency}
            Date: {datetime.now().strftime('%Y-%m-%d')}

            Use the Stock Data Fetcher tool with the ETF symbols.
            For India: use Nifty sectoral indices as proxies where direct ETF data is unavailable.
            """,
            expected_output=f"""Return a JSON object matching this exact schema:
            {{
              "sector": "{sector}",
              "market": "{market}",
              "funds": [
                {{
                  "symbol": "{primary_etf}",
                  "name": "Full ETF name",
                  "current_nav": 195.0,
                  "currency": "{currency}",
                  "expense_ratio": 0.13,
                  "aum": "$50B",
                  "change_percent": 3.2,
                  "recommendation_score": 8.5,
                  "reasoning": "2-3 sentence explanation of why this ETF is recommended"
                }}
              ]
            }}
            Include exactly 3 funds. Set expense_ratio and aum to null if not available from yfinance.
            All numeric fields must be numbers, not strings.""",
            agent=agent,
            output_pydantic=SectorFundsOutput,
        )