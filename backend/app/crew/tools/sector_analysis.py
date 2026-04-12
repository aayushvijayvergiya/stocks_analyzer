from crewai.tools import BaseTool
from typing import Type, Dict, List, Optional
from pydantic import BaseModel, Field
import yfinance as yf
from datetime import datetime, timedelta
from app.utils.logger import get_logger
from .utils import format_large_number, safe_float

logger = get_logger(__name__)

# US Sector ETF Mapping (SPDR Select Sector ETFs)
US_SECTOR_ETFS = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Consumer Discretionary": "XLY",
    "Industrials": "XLI",
    "Energy": "XLE",
    "Materials": "XLB",
    "Consumer Staples": "XLP",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC"
}

# India Nifty Sectoral Indices (as proxy)
INDIA_SECTOR_INDICES = {
    "Technology": "^CNXIT",  # Nifty IT Index
    "Banking": "^NSEBANK",   # Nifty Bank Index
    "Financial Services": "^CNXFIN",  # Nifty Financial Services
    "Auto": "^CNXAUTO",      # Nifty Auto Index
    "Pharma": "^CNXPHARMA",  # Nifty Pharma Index
    "FMCG": "^CNXFMCG",      # Nifty FMCG Index
    "Metal": "^CNXMETAL",    # Nifty Metal Index
    "Realty": "^CNXREALTY",  # Nifty Realty Index
    "Media": "^CNXMEDIA",    # Nifty Media Index
    "PSU Bank": "^CNXPSUBANK" # Nifty PSU Bank Index
}

# Map stock sectors to ETFs/Indices
def get_sector_symbol(sector: str, market: str) -> Optional[str]:
    """Get ETF/Index symbol for a given sector and market."""
    if market == "US":
        return US_SECTOR_ETFS.get(sector)
    elif market == "IN":
        # Try exact match first
        if sector in INDIA_SECTOR_INDICES:
            return INDIA_SECTOR_INDICES.get(sector)
        # Try fuzzy matching
        sector_lower = sector.lower()
        if "tech" in sector_lower or "it" in sector_lower:
            return INDIA_SECTOR_INDICES["Technology"]
        elif "bank" in sector_lower or "financ" in sector_lower:
            return INDIA_SECTOR_INDICES["Banking"]
        elif "pharma" in sector_lower or "health" in sector_lower:
            return INDIA_SECTOR_INDICES["Pharma"]
        elif "auto" in sector_lower:
            return INDIA_SECTOR_INDICES["Auto"]
    return None



class SectorPerformanceInput(BaseModel):
    """Input schema for sector performance tool."""
    market: str = Field(..., description="Market: 'US' or 'IN'")
    timeframe: str = Field(default="30d", description="Timeframe: '7d', '30d', '90d'")
    top_n: int = Field(default=3, description="Number of top sectors to return")

class SectorPerformanceTool(BaseTool):
    name: str = "Sector Performance Analyzer"
    description: str = """Analyze and rank sector performance for US or India markets.
    Returns top performing sectors with percentage gains, momentum, and trends.
    Use this to identify which sectors are leading the market."""
    args_schema: Type[BaseModel] = SectorPerformanceInput
    
    def _run(self, market: str, timeframe: str = "30d", top_n: int = 3) -> str:
        """Analyze sector performance and return rankings."""
        
        if market == "US":
            sectors_map = US_SECTOR_ETFS
        elif market == "IN":
            sectors_map = INDIA_SECTOR_INDICES
        else:
            return f"Invalid market: {market}. Must be 'US' or 'IN'."
        
        logger.info(f"Analyzing {market} sector performance for {timeframe}")
        
        # Fetch performance for all sectors
        sector_performance = []
        
        for sector_name, symbol in sectors_map.items():
            try:
                perf = self._get_sector_performance(symbol, sector_name, timeframe)
                if perf:
                    sector_performance.append(perf)
            except Exception as e:
                logger.warning(f"Failed to fetch {sector_name} ({symbol}): {e}")
                continue
        
        if not sector_performance:
            return f"Unable to fetch sector performance data for {market} market."
        
        # Sort by performance (descending)
        sector_performance.sort(key=lambda x: x["performance_pct"], reverse=True)
        
        # Format results
        result = f"Sector Performance Analysis - {market} Market ({timeframe}):\n"
        result += "=" * 60 + "\n\n"
        
        for i, sector in enumerate(sector_performance[:top_n], 1):
            result += f"#{i} {sector['name']}\n"
            result += f"   Symbol: {sector['symbol']}\n"
            result += f"   Performance: {sector['performance_pct']:+.2f}%\n"
            result += f"   Current Price: {sector['current_price']:.2f}\n"
            result += f"   Volatility: {sector['volatility']:.2f}%\n"
            result += f"   Trend: {sector['trend']}\n"
            result += f"   Momentum: {sector['momentum']}\n\n"
        
        # Summary
        top_sector = sector_performance[0]
        result += f"\nKey Insight: {top_sector['name']} is leading with "
        result += f"{top_sector['performance_pct']:+.2f}% gain over {timeframe}.\n"
        
        return result
    
    def _get_sector_performance(self, symbol: str, name: str, timeframe: str) -> Optional[Dict]:
        """Fetch performance data for a single sector ETF/Index."""
        try:
            ticker = yf.Ticker(symbol)
            
            # Map timeframe to period
            period_map = {"7d": "7d", "30d": "1mo", "90d": "3mo"}
            period = period_map.get(timeframe, "1mo")
            
            # Get historical data
            hist = ticker.history(period=period)
            
            if hist.empty:
                return None
            
            # Calculate performance
            start_price = hist['Close'].iloc[0]
            end_price = hist['Close'].iloc[-1]
            performance_pct = ((end_price - start_price) / start_price) * 100
            
            # Calculate volatility (standard deviation of daily returns)
            returns = hist['Close'].pct_change().dropna()
            volatility = returns.std() * 100
            
            # Determine trend
            if performance_pct > 5:
                trend = "Strong Uptrend"
            elif performance_pct > 0:
                trend = "Uptrend"
            elif performance_pct > -5:
                trend = "Downtrend"
            else:
                trend = "Strong Downtrend"
            
            # Momentum (simple: positive if last week > previous week)
            if len(hist) >= 14:
                recent_avg = hist['Close'].iloc[-7:].mean()
                previous_avg = hist['Close'].iloc[-14:-7].mean()
                momentum = "Accelerating" if recent_avg > previous_avg else "Decelerating"
            else:
                momentum = "Neutral"
            
            return {
                "name": name,
                "symbol": symbol,
                "performance_pct": performance_pct,
                "current_price": end_price,
                "volatility": volatility,
                "trend": trend,
                "momentum": momentum
            }
        
        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
            return None


class SectorStocksInput(BaseModel):
    """Input schema for finding stocks in a sector."""
    sector: str = Field(..., description="Sector name (e.g., 'Technology', 'Banking')")
    market: str = Field(..., description="Market: 'US' or 'IN'")
    limit: int = Field(default=10, description="Max number of stocks to return")

class SectorStocksMapperTool(BaseTool):
    name: str = "Sector Stocks Finder"
    description: str = """Find top stocks within a specific sector for US or India markets.
    Returns list of major stocks in the sector with current prices and basic metrics.
    Use after identifying top sectors to find individual stock opportunities."""
    args_schema: Type[BaseModel] = SectorStocksInput
    
    def _run(self, sector: str, market: str, limit: int = 10) -> str:
        """Find stocks in a given sector."""
        
        # Pre-defined lists of major stocks by sector
        # TODO: Replace with dynamic scraping or API in v2
        
        stocks = self._get_sector_stocks(sector, market)
        
        if not stocks:
            return f"No stock mapping found for sector '{sector}' in {market} market. Try a different sector name."
        
        result = f"Top Stocks in {sector} Sector ({market} Market):\n"
        result += "=" * 60 + "\n\n"
        
        # Fetch data for each stock — cap at 5 to avoid blocking the crew timeout
        stock_data = []
        for symbol in stocks[:min(limit, 5)]:
            try:
                data = self._get_stock_summary(symbol)
                if data:
                    stock_data.append(data)
            except Exception as e:
                logger.warning(f"Failed to fetch {symbol}: {e}")
                continue
        
        # Sort by market cap (largest first)
        stock_data.sort(key=lambda x: x.get("market_cap_raw", 0), reverse=True)
        
        for i, stock in enumerate(stock_data, 1):
            result += f"{i}. {stock['name']} ({stock['symbol']})\n"
            result += f"   Price: {stock['price']:.2f} {stock['currency']}\n"
            result += f"   Market Cap: {stock['market_cap']}\n"
            result += f"   P/E Ratio: {stock['pe']}\n\n"
        
        return result
    
    def _get_sector_stocks(self, sector: str, market: str) -> List[str]:
        """Get list of stock symbols for a sector.
        
        TODO: Make this dynamic using sector ETF holdings or market screeners.
        """
        
        # US Stocks by Sector (Top 10 each)
        US_STOCKS = {
            "Technology": ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AVGO", "CSCO", "ADBE", "CRM", "INTC"],
            "Healthcare": ["UNH", "JNJ", "LLY", "ABBV", "MRK", "TMO", "ABT", "PFE", "DHR", "BMY"],
            "Financials": ["JPM", "BAC", "WFC", "GS", "MS", "C", "AXP", "BLK", "SPGI", "USB"],
            "Consumer Discretionary": ["AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "SBUX", "TJX", "BKNG", "CMG"],
            "Industrials": ["CAT", "BA", "HON", "UNP", "RTX", "UPS", "DE", "LMT", "GE", "MMM"],
            "Energy": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "HAL"],
            "Materials": ["LIN", "APD", "SHW", "ECL", "FCX", "NEM", "CTVA", "DD", "DOW", "NUE"],
            "Consumer Staples": ["PG", "KO", "PEP", "WMT", "COST", "PM", "MO", "MDLZ", "CL", "KMB"],
            "Utilities": ["NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "PEG", "XEL", "ED"],
            "Real Estate": ["PLD", "AMT", "CCI", "EQIX", "PSA", "WELL", "DLR", "O", "SBAC", "AVB"],
            "Communication Services": ["GOOGL", "META", "NFLX", "DIS", "CMCSA", "VZ", "T", "TMUS", "EA", "TTWO"]
        }
        
        # India Stocks by Sector (Top 10 each)
        INDIA_STOCKS = {
            "Technology": ["TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS", "LTI.NS", "COFORGE.NS", "MPHASIS.NS", "PERSISTENT.NS", "LTTS.NS"],
            "Banking": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS", "AXISBANK.NS", "INDUSINDBK.NS", "BANKBARODA.NS", "PNB.NS", "IDFCFIRSTB.NS", "FEDERALBNK.NS"],
            "Financial Services": ["HDFCBANK.NS", "ICICIBANK.NS", "BAJFINANCE.NS", "BAJAJFINSV.NS", "SBILIFE.NS", "HDFCLIFE.NS", "ICICIGI.NS", "SBICARD.NS", "CHOLAFIN.NS", "MUTHOOTFIN.NS"],
            "Auto": ["MARUTI.NS", "TATAMOTORS.NS", "M&M.NS", "BAJAJ-AUTO.NS", "EICHERMOT.NS", "HEROMOTOCO.NS", "TVSMOTOR.NS", "ASHOKLEY.NS", "BALKRISIND.NS", "MRF.NS"],
            "Pharma": ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS", "AUROPHARMA.NS", "LUPIN.NS", "BIOCON.NS", "ZYDUSLIFE.NS", "TORNTPHARM.NS", "ALKEM.NS"],
            "FMCG": ["HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "BRITANNIA.NS", "DABUR.NS", "MARICO.NS", "GODREJCP.NS", "COLPAL.NS", "TATACONSUM.NS", "EMAMILTD.NS"],
            "Metal": ["TATASTEEL.NS", "HINDALCO.NS", "JSWSTEEL.NS", "COALINDIA.NS", "VEDL.NS", "HINDZINC.NS", "NMDC.NS", "SAIL.NS", "JINDALSTEL.NS", "APOLLOTYRE.NS"],
            "Realty": ["DLF.NS", "GODREJPROP.NS", "OBEROIRLTY.NS", "PRESTIGE.NS", "PHOENIXLTD.NS", "BRIGADE.NS", "SOBHA.NS", "IBREALEST.NS", "MAHLIFE.NS", "LODHA.NS"],
            "Media": ["ZEEL.NS", "SUNTV.NS", "PVRINOX.NS", "DISHTV.NS", "TV18BRDCST.NS", "NETWORK18.NS", "NAZARA.NS", "SAREGAMA.NS", "TIPS.NS", "EROSMEDIA.NS"],
            "PSU Bank": ["SBIN.NS", "BANKBARODA.NS", "PNB.NS", "CANBK.NS", "UNIONBANK.NS", "BANKINDIA.NS", "CENTRALBK.NS", "INDIANB.NS", "MAHABANK.NS", "IOB.NS"]
        }
        
        if market == "US":
            return US_STOCKS.get(sector, [])
        elif market == "IN":
            return INDIA_STOCKS.get(sector, [])
        return []
    
    def _get_stock_summary(self, symbol: str) -> Optional[Dict]:
        """Get basic summary for a stock."""
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # Handle different currency
            currency = "INR" if ".NS" in symbol or ".BO" in symbol else "USD"
            
            return {
                "symbol": symbol,
                "name": info.get("longName", info.get("shortName", symbol)),
                "price": safe_float(info.get("currentPrice", 0)),
                "currency": currency,
                "market_cap": format_large_number(safe_float(info.get("marketCap", 0))),
                "market_cap_raw": safe_float(info.get("marketCap", 0)),
                "pe": f"{safe_float(info.get('trailingPE', 0)):.2f}" if info.get('trailingPE') else "N/A"
            }
        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
            return None