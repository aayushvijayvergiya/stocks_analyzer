from typing import List, Optional
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        case_sensitive=False,
        extra='ignore'  # Ignore extra fields in .env
    )

    # LLM Config
    LLM_PROVIDER: str = Field(default="openrouter", description="openrouter/openai/groq/ollama")
    OPENROUTER_API_KEY: Optional[SecretStr] = None
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENAI_API_KEY: Optional[SecretStr] = None
    GROQ_API_KEY: Optional[SecretStr] = None
    LLM_MODEL_NAME: str = "google/gemma-4-31b-it:free"
    INTENT_MODEL_NAME: str = "meta-llama/llama-3.2-3b-instruct:free"  # fast small model for intent classification

    # Data Sources
    NEWS_API_KEY: Optional[SecretStr] = None
    SERPER_API_KEY: Optional[str] = None

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # API Config
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: List[str] = [
        'http://localhost:3000',
        'http://localhost:5173'
    ]

    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60

    # Caching TTLs (seconds)
    CACHE_TTL_STOCKS: int = 300
    CACHE_TTL_CHAT: int = 300

    # Crew Config
    # Per-crew subprocess hard timeout. With prefetched data and max_iter=2
    # each crew should complete in 15–30s; 90s gives generous headroom.
    CREW_TIMEOUT_SECONDS: int = 90
    
    VERSION: str = "1.0.0"


settings = Settings()