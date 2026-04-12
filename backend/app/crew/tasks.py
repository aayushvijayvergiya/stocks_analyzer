import json

from crewai import Task
from app.crew.output_models import (
    SectorStocksOutput,
    ChatAnswerOutput,
    SectorFundsOutput,
)

class FinancialTasks:
    """Factory class for creating financial analysis tasks."""
    
    @staticmethod
    def find_top_stocks_in_sector(
        agent,
        sector: str,
        market: str,
        timeframe: str,
        prefetched_stocks: list,
    ) -> Task:
        """Task: Rank the top 3 stocks from a PRE-FETCHED list.

        The agent does NOT call tools. All financial data is already embedded
        in the task description as a JSON list. The agent's sole job is to
        pick the top 3 and output the required Pydantic schema.
        """
        data_block = json.dumps(prefetched_stocks, indent=2, default=str)
        return Task(
            description=f"""You are given a list of pre-fetched stocks in the {sector} sector
of the {market} market over the {timeframe} timeframe. All prices, P/E ratios, EPS, ROE,
market cap, and debt/equity values below are already correct — do NOT call any tools.

PREFETCHED STOCK DATA (JSON):
{data_block}

Your task:
1. From this list ONLY, pick the 3 best stocks, ranked by a blended view of:
   - change_pct over {timeframe} (recent momentum)
   - pe_ratio and eps (valuation)
   - roe (quality)
   - market_cap (stability — larger is safer)
2. For each pick, write a 2–3 sentence "reasoning" string that cites specific
   numbers from the data block above (e.g. "P/E of 28.5 with +5.2% over 30d").
3. Output the final JSON object matching the schema below and NOTHING ELSE.

Sector: {sector}
Market: {market}
Timeframe: {timeframe}

CRITICAL OUTPUT RULES:
- Your FINAL answer must be ONLY a valid JSON object matching the schema.
- Do NOT wrap the JSON in markdown fences.
- Do NOT include any "thought", "action", "observation", or "Final Answer:" prefix.
- Do NOT call any tools — you have none.
""",
            expected_output=f"""A JSON object exactly matching this schema:
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
      "reasoning": "2-3 sentence explanation citing specific metrics",
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
Exactly 3 stocks. Numeric fields must be numbers, not strings. Use null where data is missing.""",
            agent=agent,
            output_pydantic=SectorStocksOutput,
        )

    @staticmethod
    def identify_top_etfs_in_sector(
        agent,
        sector: str,
        market: str,
        timeframe: str,
        prefetched_etfs: list,
    ) -> Task:
        """Task: Rank the top 3 ETFs/funds from a PRE-FETCHED list. No tools used."""
        currency = "USD" if market == "US" else "INR"
        data_block = json.dumps(prefetched_etfs, indent=2, default=str)
        return Task(
            description=f"""You are given pre-fetched ETF / sector-index data for the {sector}
sector of the {market} market over the {timeframe} timeframe. All NAV, expense ratios,
AUM, and % change values are already correct — do NOT call any tools.

PREFETCHED FUND DATA (JSON):
{data_block}

Your task:
1. From this list ONLY, pick the 3 best funds ranked by change_pct, expense_ratio
   (lower is better), and market_cap / aum (larger is more liquid).
2. For each pick, write a 2–3 sentence reasoning that cites the specific numbers.
3. Output the final JSON object matching the schema below and NOTHING ELSE.

Sector: {sector}
Market: {market}
Timeframe: {timeframe}
Currency: {currency}

CRITICAL OUTPUT RULES:
- Your FINAL answer must be ONLY a valid JSON object matching the schema.
- Do NOT wrap the JSON in markdown fences.
- Do NOT include any ReAct-format fields (thought/action/observation).
- Do NOT call any tools — you have none.
""",
            expected_output=f"""A JSON object exactly matching this schema:
{{
  "sector": "{sector}",
  "market": "{market}",
  "funds": [
    {{
      "symbol": "XLK",
      "name": "Full ETF name",
      "current_nav": 195.0,
      "currency": "{currency}",
      "expense_ratio": 0.13,
      "aum": "$50B",
      "change_percent": 3.2,
      "recommendation_score": 8.5,
      "reasoning": "2-3 sentence explanation citing specific performance figures"
    }}
  ]
}}
Exactly 3 funds. Set expense_ratio and aum to null if not in the data. Numeric fields must be numbers.""",
            agent=agent,
            output_pydantic=SectorFundsOutput,
        )

    @staticmethod
    def synthesize_chat_response(
        agent,
        user_question: str,
        stock_symbol: str,
        market: str,
        prefetched_snapshot: dict,
        prefetched_news: list,
    ) -> Task:
        """Task: Answer user's question using ONLY the prefetched data. No tools."""
        snapshot_block = json.dumps(prefetched_snapshot or {}, indent=2, default=str)
        news_block = json.dumps(prefetched_news or [], indent=2, default=str)

        return Task(
            description=f"""Answer the user's question about {stock_symbol} using ONLY the
pre-fetched data below. Do NOT call any tools.

User Question: "{user_question}"
Stock Symbol: {stock_symbol}
Market: {market}

PREFETCHED STOCK SNAPSHOT (JSON):
{snapshot_block}

PREFETCHED NEWS (JSON):
{news_block}

Your approach:
1. Read the snapshot and news above.
2. Write a 200–400 word conversational answer that cites specific numbers from the snapshot.
3. Build the `sources` list from the news titles and links above.
4. Fill `agent_reasoning` with a one-line explanation of your logic.

CRITICAL OUTPUT RULES:
- Return ONLY the JSON object matching the schema below.
- Do NOT wrap it in markdown fences.
- Do NOT include ReAct-format fields.
- Do NOT call any tools — you have none.
""",
            expected_output=f"""A JSON object exactly matching this schema:
{{
  "response": "Your conversational answer (200-400 words) citing specific numbers",
  "sources": [
    {{
      "title": "Article title from prefetched news",
      "url": "https://source-url.com",
      "date": "YYYY-MM-DD"
    }}
  ],
  "agent_reasoning": "One-line explanation of how you arrived at this answer"
}}
`sources` may be an empty list if prefetched_news was empty.""",
            agent=agent,
            output_pydantic=ChatAnswerOutput,
        )
