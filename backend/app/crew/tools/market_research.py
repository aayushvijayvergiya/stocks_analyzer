from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field
from ddgs import DDGS
import httpx
from datetime import datetime, timedelta

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

class WebSearchInput(BaseModel):
    """Input schema for web search tool."""
    query: str = Field(..., description="Search query (e.g., 'Apple stock news today')")
    max_results: int = Field(default=5, description="Maximum number of results to return")
    time_range: str = Field(default="d", description="Time range: d=day, w=week, m=month")

class WebSearchTool(BaseTool):
    name: str = "Web Search"
    description: str = """Search the web for recent news and information about stocks, sectors, or market events.
    Returns titles, URLs, snippets from recent articles. Use for gathering latest market news and sentiment."""
    args_schema: Type[BaseModel] = WebSearchInput
    
    def _run(self, query: str, max_results: int = 5, time_range: str = "d") -> str:
        """Execute web search using DuckDuckGo (free) or Serper API if key available."""
        
        # Try Serper first if API key available (better results)
        if settings.SERPER_API_KEY:
            try:
                return self._search_with_serper(query, max_results)
            except Exception as e:
                logger.warning(f"Serper API failed: {e}, falling back to DuckDuckGo")
        
        # Fallback to DuckDuckGo (always free)
        return self._search_with_duckduckgo(query, max_results, time_range)
    
    def _search_with_duckduckgo(self, query: str, max_results: int, time_range: str) -> str:
        """Search using DuckDuckGo (free, no API key needed)."""
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results, timelimit=time_range))
            
            if not results:
                return f"No results found for query: {query}"
            
            # Format results
            formatted = f"Web Search Results for '{query}':\n\n"
            for i, result in enumerate(results, 1):
                formatted += f"{i}. {result.get('title', 'No title')}\n"
                formatted += f"   URL: {result.get('href', 'N/A')}\n"
                formatted += f"   Snippet: {result.get('body', 'N/A')[:200]}...\n\n"
            
            return formatted
        
        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")
            return f"Search failed: {str(e)}"
    
    def _search_with_serper(self, query: str, max_results: int) -> str:
        """Search using Serper API (requires API key, better for stock/financial news)."""
        url = "https://google.serper.dev/search"
        payload = {"q": query, "num": max_results}
        headers = {
            "X-API-KEY": settings.SERPER_API_KEY,
            "Content-Type": "application/json"
        }
        
        response = httpx.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Format results
        formatted = f"Web Search Results for '{query}':\n\n"
        
        # Organic results
        for i, result in enumerate(data.get("organic", [])[:max_results], 1):
            formatted += f"{i}. {result.get('title', 'No title')}\n"
            formatted += f"   URL: {result.get('link', 'N/A')}\n"
            formatted += f"   Snippet: {result.get('snippet', 'N/A')}\n\n"
        
        # News results if available
        if "news" in data and data["news"]:
            formatted += "\nRecent News:\n"
            for i, news in enumerate(data["news"][:3], 1):
                formatted += f"- {news.get('title')}\n"
                formatted += f"  Source: {news.get('source')} | {news.get('date', 'N/A')}\n\n"
        
        return formatted
    
    
class NewsSearchInput(BaseModel):
    """Input schema for news search tool."""
    query: str = Field(..., description="News search query (stock name, ticker, or topic)")
    days_back: int = Field(default=7, description="Number of days to look back")
    language: str = Field(default="en", description="Language code (en for English)")

class NewsAPITool(BaseTool):
    name: str = "Financial News Search"
    description: str = """Search for news articles specifically about stocks, companies, or financial topics.
    Returns recent news with titles, sources, publication dates, and URLs.
    Best for getting structured news data about specific companies."""
    args_schema: Type[BaseModel] = NewsSearchInput
    
    def _run(self, query: str, days_back: int = 7, language: str = "en") -> str:
        """Fetch news using NewsAPI if key available, else fallback to web search."""
        
        if not settings.NEWS_API_KEY:
            logger.info("NewsAPI key not available, using web search fallback")
            # Fallback to web search with news-specific query
            web_tool = WebSearchTool()
            return web_tool._run(query=f"{query} stock news", max_results=10, time_range="w")
        
        try:
            return self._fetch_from_newsapi(query, days_back, language)
        except Exception as e:
            logger.error(f"NewsAPI failed: {e}")
            # Fallback to web search
            web_tool = WebSearchTool()
            return web_tool._run(query=f"{query} stock news", max_results=10, time_range="w")
    
    def _fetch_from_newsapi(self, query: str, days_back: int, language: str) -> str:
        """Fetch news from NewsAPI."""
        url = "https://newsapi.org/v2/everything"
        
        from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        
        params = {
            "q": query,
            "from": from_date,
            "language": language,
            "sortBy": "publishedAt",
            "pageSize": 20,
            "apiKey": settings.NEWS_API_KEY
        }
        
        response = httpx.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        articles = data.get("articles", [])
        
        if not articles:
            return f"No news found for '{query}' in the last {days_back} days."
        
        # Format results
        formatted = f"News Articles for '{query}' (Last {days_back} days):\n\n"
        for i, article in enumerate(articles[:15], 1):
            formatted += f"{i}. {article.get('title', 'No title')}\n"
            formatted += f"   Source: {article.get('source', {}).get('name', 'Unknown')}\n"
            formatted += f"   Published: {article.get('publishedAt', 'N/A')[:10]}\n"
            formatted += f"   URL: {article.get('url', 'N/A')}\n"
            formatted += f"   Description: {article.get('description', 'N/A')[:150]}...\n\n"
        
        return formatted
    
    
class SentimentAnalysisInput(BaseModel):
    """Input schema for sentiment analysis."""
    headlines: list[str] = Field(..., description="List of news headlines to analyze")

class SentimentAnalysisTool(BaseTool):
    name: str = "News Sentiment Analyzer"
    description: str = """Analyze sentiment of news headlines and articles.
    Returns overall sentiment (positive/negative/neutral) and sentiment score.
    Use after gathering news to determine market sentiment."""
    args_schema: Type[BaseModel] = SentimentAnalysisInput
    
    def _run(self, headlines: list[str]) -> str:
        """Analyze sentiment using simple keyword-based approach.
        
        TODO: Upgrade to transformer-based sentiment analysis (FinBERT) for v2.
        """
        if not headlines:
            return "No headlines provided for sentiment analysis."
        
        positive_keywords = [
            "surge", "rally", "gain", "profit", "growth", "beat", "upgrade",
            "strong", "bullish", "rise", "success", "record", "high", "boost",
            "outperform", "soar", "jump", "breakthrough", "positive", "wins"
        ]
        
        negative_keywords = [
            "fall", "drop", "loss", "decline", "weak", "bearish", "crash",
            "plunge", "miss", "downgrade", "concern", "risk", "warning",
            "struggle", "cut", "layoff", "lawsuit", "investigation", "negative"
        ]
        
        neutral_keywords = [
            "flat", "unchanged", "stable", "hold", "steady", "maintain"
        ]
        
        sentiments = []
        
        for headline in headlines:
            headline_lower = headline.lower()
            
            pos_count = sum(1 for word in positive_keywords if word in headline_lower)
            neg_count = sum(1 for word in negative_keywords if word in headline_lower)
            neu_count = sum(1 for word in neutral_keywords if word in headline_lower)
            
            if pos_count > neg_count:
                sentiments.append(("positive", pos_count))
            elif neg_count > pos_count:
                sentiments.append(("negative", neg_count))
            else:
                sentiments.append(("neutral", neu_count))
        
        # Calculate overall sentiment
        positive = sum(1 for s, _ in sentiments if s == "positive")
        negative = sum(1 for s, _ in sentiments if s == "negative")
        neutral = sum(1 for s, _ in sentiments if s == "neutral")
        
        total = len(sentiments)
        pos_pct = (positive / total) * 100
        neg_pct = (negative / total) * 100
        neu_pct = (neutral / total) * 100
        
        # Determine overall sentiment
        if pos_pct > 60:
            overall = "STRONGLY POSITIVE"
        elif pos_pct > 40:
            overall = "POSITIVE"
        elif neg_pct > 60:
            overall = "STRONGLY NEGATIVE"
        elif neg_pct > 40:
            overall = "NEGATIVE"
        else:
            overall = "NEUTRAL"
        
        # Sentiment score (-100 to +100)
        sentiment_score = pos_pct - neg_pct
        
        result = f"""
Sentiment Analysis Results:
===========================
Total Headlines Analyzed: {total}

Breakdown:
- Positive: {positive} ({pos_pct:.1f}%)
- Negative: {negative} ({neg_pct:.1f}%)
- Neutral: {neutral} ({neu_pct:.1f}%)

Overall Sentiment: {overall}
Sentiment Score: {sentiment_score:+.1f} (-100 to +100 scale)

Interpretation:
"""
        
        if sentiment_score > 30:
            result += "Strong bullish sentiment. Market appears optimistic about this stock."
        elif sentiment_score > 10:
            result += "Moderately positive sentiment. Generally favorable news coverage."
        elif sentiment_score > -10:
            result += "Mixed sentiment. News is balanced between positive and negative."
        elif sentiment_score > -30:
            result += "Moderately negative sentiment. Some concerns in recent news."
        else:
            result += "Strong bearish sentiment. Significant negative news coverage."
        
        return result