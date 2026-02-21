

from openai import BaseModel


from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field
import yfinance as yf
from datetime import datetime, timedelta

class PortfolioDataInput(BaseModel):
    """Input for fetching multiple stocks at once."""
    symbols: list[str] = Field(..., description="List of stock symbols")
    timeframe: str = Field(default="30d", description="Timeframe for comparison")

class PortfolioDataTool(BaseTool):
    name: str = "Multi-Stock Data Fetcher"
    description: str = """Fetch data for multiple stocks simultaneously for comparison.
    Useful for ranking and selecting top performers."""
    args_schema: Type[BaseModel] = PortfolioDataInput
    
    def _run(self, symbols: list[str], timeframe: str = "30d") -> str:
        """Fetch and compare multiple stocks."""
        # Use yfinance download for batch fetching
        # Return comparative analysis
        try:
            data = yf.download(symbols, period=timeframe)
            # Process data to create comparative insights
            output = f"Comparative Data for {', '.join(symbols)} over {timeframe}:\n"
            output += str(data)
            return output
        except Exception as e:
            return f"Error fetching data for symbols {', '.join(symbols)}: {str(e)}"

class StockDataInput(BaseModel):
    """Input schema for stock data tool."""
    symbol: str = Field(..., description="Stock symbol (e.g., AAPL, RELIANCE.NS)")
    metrics: list[str] = Field(
        default=["price", "metrics", "info"],
        description="Metrics to fetch: price, metrics, info, history"
    )
    
    
class YFinanceDataTool(BaseTool):
    name: str = "Stock Data Fetcher"
    description: str = """Fetches real-time stock data for US and India markets.
    Supports: current price, financial metrics (P/E, EPS, ROE, etc.), company info, historical data.
    For India stocks, append .NS (NSE) or .BO (BSE) to symbol."""
    args_schema: Type[BaseModel] = StockDataInput
    
    def _run(self, symbol: str, metrics: list[str] = ["price", "metrics", "info"]) -> str:
        """Execute the tool to fetch stock data."""
        # Implement fetching logic
        # Return formatted string with all requested data
        try:
            stock = yf.Ticker(symbol)
            output = f"Stock Data for {symbol}:\n"
            if "price" in metrics:
                price = stock.info.get("currentPrice", "N/A")
                output += f"Current Price: {price}\n"
            if "metrics" in metrics:
                pe_ratio = stock.info.get("trailingPE", "N/A")
                eps = stock.info.get("trailingEps", "N/A")
                roe = stock.info.get("returnOnEquity", "N/A")
                output += f"P/E Ratio: {pe_ratio}\nEPS: {eps}\nROE: {roe}\n"
            if "info" in metrics:
                name = stock.info.get("longName", "N/A")
                sector = stock.info.get("sector", "N/A")
                industry = stock.info.get("industry", "N/A")
                output += f"Company Name: {name}\nSector: {sector}\nIndustry: {industry}\n"
            if "history" in metrics:
                end_date = datetime.now()
                start_date = end_date - timedelta(days=30)
                history = stock.history(start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))
                output += f"Historical Data (Last 30 days):\n{history[['Open', 'Close', 'Volume']]}\n"
            return output
        except Exception as e:
            return f"Error fetching data for {symbol}: {str(e)}"
        
        
    def fetch_current_price(self, ticker: yf.Ticker) -> str:
        """Fetch current price of the stock."""
        try:
            price = ticker.info.get("currentPrice", "N/A")
            return f"Current Price: {price}"
        except Exception as e:
            return f"Error fetching price: {str(e)}"
        
        
    def fetch_financial_metrics(self, ticker: yf.Ticker) -> str:
        """Fetch financial metrics like P/E ratio, EPS, ROE."""
        try:
            pe_ratio = ticker.info.get("trailingPE", "N/A")
            eps = ticker.info.get("trailingEps", "N/A")
            roe = ticker.info.get("returnOnEquity", "N/A")
            market_cap = ticker.info.get("marketCap", "N/A")
            debt_to_equity = ticker.info.get("debtToEquity", "N/A")
            fifty_two_week_high = ticker.info.get("fiftyTwoWeekHigh", "N/A")
            dividend_yield = ticker.info.get("dividendYield", "N/A")
            
            return f"P/E Ratio: {pe_ratio}\nEPS: {eps}\nROE: {roe}\nMarket Cap: {market_cap}\nDebt to Equity: {debt_to_equity}\n52-Week High: {fifty_two_week_high}\nDividend Yield: {dividend_yield}"
        except Exception as e:
            return f"Error fetching financial metrics: {str(e)}"
        
        
    def fetch_company_info(self, ticker: yf.Ticker) -> str:
        """Fetch company information like name, sector, industry."""
        try:
            name = ticker.info.get("longName", "N/A")
            sector = ticker.info.get("sector", "N/A")
            industry = ticker.info.get("industry", "N/A")
            description = ticker.info.get("longBusinessSummary", "N/A")
            website = ticker.info.get("website", "N/A")
            country = ticker.info.get("country", "N/A")

            return f"Company Name: {name}\nSector: {sector}\nIndustry: {industry}\nDescription: {description}\nWebsite: {website}\nCountry: {country}"
        except Exception as e:
            return f"Error fetching company info: {str(e)}"
        
        
    def fetch_historical_data(self, ticker: yf.Ticker, period: str = "30d") -> str:
        """Fetch historical stock data for the last 30 days."""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=int(period.replace("d", "")))
            history = ticker.history(start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d"))
            return f"Historical Data (Last {period}):\n{history[['Open', 'Close', 'Volume']]}"
        except Exception as e:
            return f"Error fetching historical data: {str(e)}"
        
        
def calculate_pe_ratio(price: float, eps: float) -> str:
    """Calculate P/E ratio given price and EPS."""
    try:
        if eps == 0:
            return "EPS is zero, P/E ratio is undefined."
        pe_ratio = price / eps
        return f"Calculated P/E Ratio: {pe_ratio:.2f}"
    except Exception as e:
        return f"Error calculating P/E ratio: {str(e)}"
    
    
def calculate_price_change_percent(current: float, previous: float) -> float:
    """Calculate percentage change."""
    try:
        if previous == 0:
            return 0.0
        change_percent = ((current - previous) / previous) * 100
        return change_percent
    except Exception as e:
        return 0.0

def assess_financial_health(metrics: dict) -> dict:
    """Score financial health (0-10) based on metrics.
    
    Scoring criteria:
    - P/E ratio: Lower is better (compare to sector avg)
    - ROE: Higher is better (>15% is good)
    - Debt/Equity: Lower is better (<1 is healthy)
    - Market Cap: Larger is more stable
    Returns: {"score": 7.5, "grade": "B+", "strengths": [...], "concerns": [...]}
    """
    score = 0
    strengths = []
    concerns = []
    
    pe_ratio = metrics.get("pe_ratio")
    roe = metrics.get("roe")
    debt_to_equity = metrics.get("debt_to_equity")
    market_cap = metrics.get("market_cap")
    
    # P/E ratio scoring
    if pe_ratio is not None:
        if pe_ratio < 15:
            score += 3
            strengths.append("Low P/E ratio indicates undervaluation.")
        elif pe_ratio < 25:
            score += 2
            strengths.append("Moderate P/E ratio.")
        else:
            concerns.append("High P/E ratio may indicate overvaluation.")
    
    # ROE scoring
    if roe is not None:
        if roe > 15:
            score += 3
            strengths.append("High ROE indicates efficient use of equity.")
        elif roe > 5:
            score += 2
            strengths.append("Moderate ROE.")
        else:
            concerns.append("Low ROE may indicate poor profitability.")
    
    # Debt/Equity scoring
    if debt_to_equity is not None:
        if debt_to_equity < 1:
            score += 2
            strengths.append("Healthy debt levels.")
        else:
            concerns.append("High debt levels may be risky.")
    
    # Market Cap scoring
    if market_cap is not None:
        if market_cap > 10e9:
            score += 2
            strengths.append("Large market cap indicates stability.")
        elif market_cap > 1e9:
            score += 1
            strengths.append("Mid-sized market cap.")
        else:
            concerns.append("Small market cap may be volatile.")
    
    # Final grading
    grade = "A" if score >= 8 else "B" if score >= 6 else "C" if score >= 4 else "D"
    
    return {"score": score, "grade": grade, "strengths": strengths, "concerns": concerns}

def compare_to_sector_average(ticker: yf.Ticker, metrics: dict) -> dict:
    """Compare stock metrics to sector ETF performance.
    
    Returns: {"sector": "Technology", "stock_pe": 28.5, "sector_avg_pe": 32.1, ...}
    """
    try:
        sector = ticker.info.get("sector", "N/A")
        if sector == "N/A":
            return {"error": "Sector information not available."}
        
        # Map sector to corresponding ETF
        sector_etf_map = {
            "Technology": "XLK",
            "Healthcare": "XLV",
            "Financial Services": "XLF",
            "Consumer Cyclical": "XLY",
            "Consumer Defensive": "XLP",
            "Energy": "XLE",
            "Industrials": "XLI",
            "Utilities": "XLU",
            "Real Estate": "XLRE",
            "Materials": "XLB"
        }
        
        etf_symbol = sector_etf_map.get(sector)
        if not etf_symbol:
            return {"error": f"No ETF mapping for sector: {sector}"}
        
        etf = yf.Ticker(etf_symbol)
        stock_pe = metrics.get("pe_ratio")
        etf_pe = etf.info.get("trailingPE", "N/A")
        
        return {
            "sector": sector,
            "stock_pe": stock_pe,
            "sector_avg_pe": etf_pe
        }
    except Exception as e:
        return {"error": f"Error comparing to sector average: {str(e)}"}