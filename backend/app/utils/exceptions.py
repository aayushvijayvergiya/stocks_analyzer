"""
Custom exception classes for the Stocks Analyzer application.
"""

from typing import Optional


class StocksAnalyzerException(Exception):
    """Base exception for all application errors."""
    
    def __init__(self, message: str, error_code: Optional[str] = None):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class ValidationError(StocksAnalyzerException):
    """Raised when input validation fails."""
    
    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(message, error_code="VALIDATION_ERROR")
        self.field = field


class SymbolNotFoundError(StocksAnalyzerException):
    """Raised when a stock symbol cannot be found."""
    
    def __init__(self, symbol: str):
        super().__init__(
            f"Stock symbol '{symbol}' not found",
            error_code="SYMBOL_NOT_FOUND"
        )
        self.symbol = symbol


class MarketDataError(StocksAnalyzerException):
    """Raised when market data cannot be retrieved."""
    
    def __init__(self, message: str, source: Optional[str] = None):
        super().__init__(message, error_code="MARKET_DATA_ERROR")
        self.source = source


class NewsAPIError(StocksAnalyzerException):
    """Raised when news API fails."""
    
    def __init__(self, message: str, api_name: Optional[str] = None):
        super().__init__(message, error_code="NEWS_API_ERROR")
        self.api_name = api_name


class CrewExecutionError(StocksAnalyzerException):
    """Raised when CrewAI execution fails."""
    
    def __init__(self, message: str, crew_type: Optional[str] = None):
        super().__init__(message, error_code="CREW_EXECUTION_ERROR")
        self.crew_type = crew_type


class RateLimitError(StocksAnalyzerException):
    """Raised when rate limit is exceeded."""
    
    def __init__(self, limit: int, window: int):
        super().__init__(
            f"Rate limit exceeded: {limit} requests per {window} seconds",
            error_code="RATE_LIMIT_EXCEEDED"
        )
        self.limit = limit
        self.window = window


class CacheError(StocksAnalyzerException):
    """Raised when cache operations fail."""
    
    def __init__(self, message: str, operation: Optional[str] = None):
        super().__init__(message, error_code="CACHE_ERROR")
        self.operation = operation


class JobNotFoundError(StocksAnalyzerException):
    """Raised when a job ID cannot be found."""
    
    def __init__(self, job_id: str):
        super().__init__(
            f"Job '{job_id}' not found or expired",
            error_code="JOB_NOT_FOUND"
        )
        self.job_id = job_id


class ServiceUnavailableError(StocksAnalyzerException):
    """Raised when a required service is unavailable."""
    
    def __init__(self, service: str, message: Optional[str] = None):
        msg = message or f"Service '{service}' is currently unavailable"
        super().__init__(msg, error_code="SERVICE_UNAVAILABLE")
        self.service = service


class LLMError(StocksAnalyzerException):
    """Raised when LLM API fails."""
    
    def __init__(self, message: str, provider: Optional[str] = None):
        super().__init__(message, error_code="LLM_ERROR")
        self.provider = provider
