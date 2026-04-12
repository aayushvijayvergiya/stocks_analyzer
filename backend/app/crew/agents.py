from crewai import Agent, LLM
from typing import Optional
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

def get_llm(temperature: float = 0.3):
    """Get configured LLM based on settings.

    Priority: OpenRouter > OpenAI > raises error
    """
    provider = settings.LLM_PROVIDER.lower()

    if provider == "openrouter" and settings.OPENROUTER_API_KEY:
        logger.info(f"Using OpenRouter LLM: {settings.LLM_MODEL_NAME}")
        return LLM(
            model=settings.LLM_MODEL_NAME,
            provider="openai",  # OpenRouter is OpenAI-compatible; use native SDK
            api_key=settings.OPENROUTER_API_KEY.get_secret_value(),
            base_url=settings.OPENROUTER_BASE_URL,
            temperature=temperature
        )

    elif provider == "openai" and settings.OPENAI_API_KEY:
        logger.info(f"Using OpenAI LLM: {settings.LLM_MODEL_NAME}")
        return LLM(
            model=settings.LLM_MODEL_NAME or "gpt-4o-mini",
            api_key=settings.OPENAI_API_KEY.get_secret_value(),
            temperature=temperature
        )

    else:
        # Fallback: try OpenRouter, then OpenAI
        if settings.OPENROUTER_API_KEY:
            logger.warning("LLM provider not configured correctly, using OpenRouter fallback")
            return LLM(
                model=settings.LLM_MODEL_NAME,
                provider="openai",
                api_key=settings.OPENROUTER_API_KEY.get_secret_value(),
                base_url=settings.OPENROUTER_BASE_URL,
                temperature=temperature
            )
        if settings.OPENAI_API_KEY:
            logger.warning("LLM provider not set or API key missing, using OpenAI fallback")
            return LLM(
                model="gpt-4o-mini",
                api_key=settings.OPENAI_API_KEY.get_secret_value(),
                temperature=temperature
            )

        raise ValueError(
            "No LLM API key configured. Set OPENROUTER_API_KEY or OPENAI_API_KEY in .env file."
        )
        
        
class FinancialAgents:
    """Factory for creating financial analysis agents.

    Active agents: financial_data_analyst (stock/fund ranking) and
    investment_advisor (chat synthesis). Both receive pre-fetched context
    in the task description and call no tools.
    """

    @staticmethod
    def financial_data_analyst() -> Agent:
        """Reasons over pre-fetched stock/ETF data. NO tools, max_iter=2."""
        return Agent(
            role="Quantitative Financial Metrics Specialist",
            goal="Rank pre-fetched stocks by the metrics supplied in the task and output strict JSON",
            backstory="""You are a quantitative analyst. Every piece of financial data you
            need — prices, P/E ratios, ROE, market cap, debt/equity — is handed to you
            inside each task description as a JSON block. Your ONLY job is to read that
            block, rank the candidates, and output the exact JSON schema requested.

            You never call tools. You never invent data. If a field is null in the
            input, you output it as null. You never output ReAct-format text; your
            final answer is always pure JSON.""",
            tools=[],
            llm=get_llm(temperature=0.2),
            verbose=True,
            allow_delegation=False,
            max_iter=2,
        )
    
    @staticmethod
    def investment_advisor() -> Agent:
        """Synthesizes prefetched data into a conversational answer. NO tools, max_iter=2."""
        return Agent(
            role="Chief Investment Strategist and Recommendation Synthesizer",
            goal="Answer user questions using only the pre-fetched context and output strict JSON",
            backstory="""You are a CIO with 20 years of experience. You never call tools —
            every piece of data you need, including stock snapshots and news articles,
            is already embedded in the task description.

            You read the prefetched context carefully, cite specific numbers in your
            answer, and always return the exact JSON schema requested. You never output
            ReAct-format fields and never invent data.""",
            tools=[],
            llm=get_llm(temperature=0.4),
            verbose=True,
            allow_delegation=False,
            max_iter=2,
        )
