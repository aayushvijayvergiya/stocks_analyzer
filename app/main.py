from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uuid
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.dependencies import close_redis_pool, get_redis, init_redis_pool
from app.models.responses import HealthResponse
from app.api.v1.router import router as v1_router
from app.utils.logger import get_logger
from app.utils.exceptions import (
    StocksAnalyzerException,
    ValidationError,
    SymbolNotFoundError,
    RateLimitError,
    JobNotFoundError,
    ServiceUnavailableError
)

logger = get_logger(__name__)

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up the Stocks Analyzer Backend...")
    await init_redis_pool()  
    logger.info("Redis connection initialized.")
    yield
    logger.info("Shutting down the Stocks Analyzer Backend...")
    await close_redis_pool()
    logger.info("Redis connection closed.")

app = FastAPI(
    title="Stocks Analyzer API",
    description="""
    AI-powered stock and fund analysis platform for India and US markets.
    
    **Features:**
    - 💬 **Stock Chat**: Ask questions about specific stocks
    - 📊 **Stock Recommendations**: Get top stock picks by sector
    - 📈 **Fund Recommendations**: Get top ETF/fund picks by sector
    
    **Markets Supported:**
    - 🇺🇸 US (NYSE, NASDAQ)
    - 🇮🇳 India (NSE, BSE)
    
    **Powered by:** CrewAI with multiple specialized AI agents
    """,
    version="1.0.0",
    openapi_url="/api/v1/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

app.add_middleware(RequestIDMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if settings.CORS_ORIGINS else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception Handlers
@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError):
    """Handle validation errors."""
    logger.warning(
        f"Validation error: {exc.message}",
        extra={
            "error_code": exc.error_code,
            "field": getattr(exc, 'field', None),
            "path": request.url.path
        }
    )
    return JSONResponse(
        status_code=400,
        content={
            "detail": exc.message,
            "error_code": exc.error_code,
            "field": getattr(exc, 'field', None),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )


@app.exception_handler(SymbolNotFoundError)
async def symbol_not_found_handler(request: Request, exc: SymbolNotFoundError):
    """Handle stock symbol not found errors."""
    logger.warning(
        f"Symbol not found: {exc.symbol}",
        extra={"error_code": exc.error_code, "symbol": exc.symbol}
    )
    return JSONResponse(
        status_code=404,
        content={
            "detail": exc.message,
            "error_code": exc.error_code,
            "symbol": exc.symbol,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )


@app.exception_handler(RateLimitError)
async def rate_limit_handler(request: Request, exc: RateLimitError):
    """Handle rate limit exceeded errors."""
    logger.warning(
        f"Rate limit exceeded",
        extra={
            "error_code": exc.error_code,
            "client": request.client.host if request.client else "unknown",
            "path": request.url.path
        }
    )
    return JSONResponse(
        status_code=429,
        content={
            "detail": exc.message,
            "error_code": exc.error_code,
            "limit": exc.limit,
            "window": exc.window,
            "timestamp": datetime.now(timezone.utc).isoformat()
        },
        headers={"Retry-After": str(exc.window)}
    )


@app.exception_handler(JobNotFoundError)
async def job_not_found_handler(request: Request, exc: JobNotFoundError):
    """Handle job not found errors."""
    logger.warning(
        f"Job not found: {exc.job_id}",
        extra={"error_code": exc.error_code, "job_id": exc.job_id}
    )
    return JSONResponse(
        status_code=404,
        content={
            "detail": exc.message,
            "error_code": exc.error_code,
            "job_id": exc.job_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )


@app.exception_handler(ServiceUnavailableError)
async def service_unavailable_handler(request: Request, exc: ServiceUnavailableError):
    """Handle service unavailable errors."""
    logger.error(
        f"Service unavailable: {exc.service}",
        extra={"error_code": exc.error_code, "service": exc.service}
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": exc.message,
            "error_code": exc.error_code,
            "service": exc.service,
            "timestamp": datetime.now(timezone.utc).isoformat()
        },
        headers={"Retry-After": "60"}
    )


@app.exception_handler(StocksAnalyzerException)
async def stocks_analyzer_exception_handler(request: Request, exc: StocksAnalyzerException):
    """Handle generic application errors."""
    logger.error(
        f"Application error: {exc.message}",
        extra={"error_code": exc.error_code, "exception": type(exc).__name__}
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": exc.message,
            "error_code": exc.error_code,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle FastAPI HTTP exceptions."""
    logger.warning(
        f"HTTP exception: {exc.detail}",
        extra={"status_code": exc.status_code, "path": request.url.path}
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error_code": f"HTTP_{exc.status_code}",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors."""
    logger.error(
        f"Unhandled exception: {str(exc)}",
        extra={
            "exception_type": type(exc).__name__,
            "path": request.url.path
        },
        exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected error occurred. Please try again later.",
            "error_code": "INTERNAL_SERVER_ERROR",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )


# Include API v1 router
app.include_router(v1_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint.
    
    Returns system health status including:
    - Overall status (healthy/degraded)
    - Redis connection status
    - Environment info
    - API version
    """
    redis_status = "disconnected"
    try:
        redis_client = await get_redis()
        if redis_client:
            redis_client.ping()
            redis_status = "connected"
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")
    
    return HealthResponse(
        status="healthy" if redis_status == "connected" else "degraded",
        environment=settings.ENVIRONMENT,
        version="1.0.0",
        redis_status=redis_status,
        timestamp=datetime.now(timezone.utc)
    )


@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint - API information.
    """
    return {
        "name": "Stocks Analyzer API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "api_v1": settings.API_V1_PREFIX,
        "health": "/health"
    }