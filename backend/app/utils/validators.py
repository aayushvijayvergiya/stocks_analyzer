import re
from app.utils.exceptions import ValidationError, SymbolNotFoundError


def validate_stock_symbol(symbol: str) -> tuple[bool, str]:
    """Validate stock symbol format.

    Returns: (is_valid, error_message)
    """
    if symbol is None:
        return False, "Symbol is required."

    normalized = symbol.strip().upper()
    if not normalized:
        return False, "Symbol is required."

    if is_valid_indian_symbol(normalized) or is_valid_us_symbol(normalized):
        return True, ""

    return False, "Invalid stock symbol format."


def is_valid_indian_symbol(symbol: str) -> bool:
    """Check if symbol is valid for Indian market."""
    if not symbol:
        return False
    # Common NSE/BSE symbols: 1-12 chars, A-Z, 0-9, & , - , .
    return re.fullmatch(r"[A-Z0-9&.-]{1,12}", symbol) is not None


def is_valid_us_symbol(symbol: str) -> bool:
    """Check if symbol is valid for US market."""
    if not symbol:
        return False
    # Common US symbols: 1-5 letters, optional dot suffix (e.g., BRK.B)
    return (
        re.fullmatch(r"[A-Z]{1,5}", symbol) is not None
        or re.fullmatch(r"[A-Z]{1,4}\.[A-Z]", symbol) is not None
    )


def validate_and_normalize_symbol(symbol: str, market: str | None = '') -> tuple[str, str]:
    """Validate and normalize stock symbol, detecting market if not provided.
    
    Args:
        symbol: Stock symbol (e.g., "AAPL", "reliance", "TCS.NS")
        market: Optional market hint ("US" or "IN")
        
    Returns:
        Tuple of (normalized_symbol, detected_market)
        
    Raises:
        ValidationError: If symbol is invalid
    """
    if not symbol:
        raise ValidationError("Stock symbol is required", field="stock_symbol")
    
    # Normalize to uppercase
    symbol = symbol.strip().upper()
    
    # Detect market from suffix if present
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        detected_market = "IN"
        normalized = symbol  # Keep the suffix
    elif "." in symbol and not symbol.endswith((".NS", ".BO")):
        # US stocks like BRK.B
        detected_market = "US"
        normalized = symbol
    elif market == "IN":
        # India market specified, add .NS suffix if missing
        detected_market = "IN"
        if not (symbol.endswith(".NS") or symbol.endswith(".BO")):
            normalized = f"{symbol}.NS"  # Default to NSE
        else:
            normalized = symbol
    else:
        # Default to US if no clear indicator
        detected_market = market if market in ["US", "IN"] else "US"
        normalized = symbol
    
    # Validate
    is_valid, error = validate_stock_symbol(normalized)
    if not is_valid:
        raise SymbolNotFoundError(symbol=symbol)
    
    return normalized, detected_market