def normalize_stock_symbol(market: str, symbol: str):
    """Normalize stock symbol for yfinance queries.
    
    Args:
        symbol: Raw stock symbol (e.g., "AAPL", "RELIANCE", "RELIANCE.NS")
        market: "US" or "IN" to force market, or None to auto-detect
    
    Returns:
        Normalized symbol (e.g., "AAPL", "RELIANCE.NS")
    """
    symbol = symbol.strip().upper()
    
    if market == "US":
        # For US stocks, just return the symbol as is
        return symbol
    elif market == "IN":
        # For Indian stocks, ensure it ends with .NS
        if not symbol.endswith(".NS"):
            return f"{symbol}.NS"
        return symbol
    else:
        # Auto-detect based on common patterns
        if symbol.endswith(".NS") or symbol.endswith(".BO") or symbol.endswith(".BSE"):
            return symbol  # Already in Indian format
        elif any(char.isdigit() for char in symbol):
            return f"{symbol}.NS"  # Likely an Indian stock
        else:
            return symbol  # Assume it's a US stock by default
        
        
def detect_market_from_symbol(symbol: str) -> str:
    """Detect if symbol is for US or India market.
    
    Returns: "US" or "IN"
    """
    symbol = symbol.strip().upper()
    if symbol.endswith(".NS") or symbol.endswith(".BO") or symbol.endswith(".BSE"):
        return "IN"
    elif any(char.isdigit() for char in symbol):
        return "IN"
    else:
        return "US"
    
    
def format_large_number(num: float) -> str:
    """Format large numbers with K, M, B, T suffixes.
    
    Examples: 1500000 -> "1.5M", 2800000000000 -> "2.8T"
    """
    abs_num = abs(num)
    if abs_num >= 1_000_000_000_000:
        return f"{num / 1_000_000_000_000:.1f}T"
    elif abs_num >= 1_000_000_000:
        return f"{num / 1_000_000_000:.1f}B"
    elif abs_num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    elif abs_num >= 1_000:
        return f"{num / 1_000:.1f}K"
    else:
        return str(num)
    
    
def safe_float(value, default: float = 0.0) -> float:
    """Safely convert value to float, return default if fails."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default
    

def get_currency_from_market(market: str) -> str:
    """Return 'USD' for US, 'INR' for India."""
    if market == "US":
        return "USD"
    elif market == "IN":
        return "INR"
    else:
        return "INR"  # Default to INR if unknown market
    