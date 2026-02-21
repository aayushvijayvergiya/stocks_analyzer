# 📊 Stocks Analyzer Backend

AI-powered stock and fund analysis platform for India and US markets, built with FastAPI and CrewAI.

[![Python Version](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128+-green.svg)](https://fastapi.tiangolo.com/)
[![CrewAI](https://img.shields.io/badge/CrewAI-1.7+-orange.svg)](https://crewai.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## 🎯 Features

- **🤖 Multi-Agent AI System**: 4 specialized AI agents powered by CrewAI
  - Market Researcher - Real-time market trends and news analysis
  - Financial Data Analyst - In-depth financial metrics and valuation
  - Sector Performance Analyst - Cross-sector comparison and rankings
  - Investment Advisor - Personalized investment recommendations

- **🌍 Dual Market Support**:
  - 🇺🇸 United States (NYSE, NASDAQ)
  - 🇮🇳 India (NSE, BSE)

- **📈 Core Capabilities**:
  - Interactive stock Q&A chat
  - Top stock recommendations by sector
  - ETF/fund recommendations by sector
  - Real-time market data via yfinance
  - News and sentiment analysis

- **⚡ Performance & Reliability**:
  - Redis caching for fast responses
  - Async job queue for long-running analyses
  - Rate limiting and request tracking
  - Structured JSON logging
  - Comprehensive error handling

## 🏗️ Architecture

```
┌─────────────────┐
│   FastAPI App   │
│   (REST API)    │
└────────┬────────┘
         │
    ┌────┴─────┬──────────┬──────────┐
    │          │          │          │
┌───▼───┐  ┌──▼──┐  ┌────▼────┐  ┌──▼──┐
│ Cache │  │ Job │  │  Crew   │  │Rate │
│Service│  │Store│  │ Service │  │Limit│
└───┬───┘  └──┬──┘  └────┬────┘  └─────┘
    │         │          │
    └─────────┴──────────┴─────────┐
                                   │
                            ┌──────▼──────┐
                            │    Redis    │
                            └──────┬──────┘
                                   │
                        ┌──────────┴──────────┐
                        │                     │
                   ┌────▼────┐          ┌────▼────┐
                   │CrewAI   │          │External │
                   │Agents(4)│          │Data APIs│
                   └─────────┘          └─────────┘
                        │                     │
                   ┌────▼────┐          ┌────▼────┐
                   │ Tools   │          │yfinance │
                   │(8 types)│          │NewsAPI  │
                   └─────────┘          │DuckDuck │
                                       └─────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher
- Redis (via Docker or local installation)
- API Keys:
  - **Groq API Key** (Free, recommended) - [Get it here](https://console.groq.com/keys)
  - **OpenAI API Key** (Optional fallback) - [Get it here](https://platform.openai.com/api-keys)

### Local Development

1. **Install dependencies**
   ```bash
   pip install uv
   uv pip install -e .
   ```

2. **Start Redis**
   ```bash
   docker run -d -p 6379:6379 redis:7-alpine
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Set GROQ_API_KEY and REDIS_URL
   ```

4. **Run**
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

   - API: http://localhost:8000
   - Interactive Docs: http://localhost:8000/docs
   - Health: http://localhost:8000/health

### Docker

```bash
docker-compose up -d
```

## 📖 API Documentation

### Endpoints

#### 1. **Chat with Stock Assistant** 
`POST /api/v1/chat`

Ask questions about specific stocks.

**Request:**
```json
{
  "stock_symbol": "AAPL",
  "message": "What's the current price and recent news?",
  "user_preferences": {
    "risk_tolerance": "moderate",
    "investment_horizon": "long-term"
  }
}
```

**Response:**
```json
{
  "response": "Apple Inc. (AAPL) is currently trading at $175.50...",
  "stock_symbol": "AAPL",
  "region": "US",
  "sources": ["yfinance", "newsapi"],
  "agent_reasoning": "Based on technical analysis and recent earnings...",
  "timestamp": "2026-02-20T10:30:00"
}
```

#### 2. **Get Stock Recommendations**
`POST /api/v1/stocks/recommendations`

Get top stock picks by sector (async job).

**Request:**
```json
{
  "timeframe": "1mo",
  "top_n": 5,
  "sector": "Technology",
  "market": "US"
}
```

**Response (Job Created):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "message": "Job submitted for processing"
}
```

**Poll Status:** `GET /api/v1/stocks/recommendations/{job_id}`

**Response (Completed):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "result": {
    "recommendations": [
      {
        "symbol": "AAPL",
        "company_name": "Apple Inc.",
        "sector": "Technology",
        "recommendation": "BUY",
        "rationale": "Strong fundamentals with...",
        "risk_level": "LOW",
        "target_price": 185.0,
        "current_price": 175.5
      }
    ],
    "region": "US",
    "sector": "Technology",
    "analysis_timestamp": "2026-02-20T10:30:00"
  },
  "created_at": "2026-02-20T10:25:00",
  "completed_at": "2026-02-20T10:30:00"
}
```

#### 3. **Get Fund/ETF Recommendations**
`POST /api/v1/funds/recommendations`

Get top ETF/fund picks by sector.

**Request:**
```json
{
  "timeframe": "3mo",
  "top_n": 5,
  "sector": "Technology",
  "market": "US"
}
```

### Market Support

- **US Stocks**: Use symbols as-is (e.g., `AAPL`, `MSFT`, `TSLA`)
- **Indian Stocks**: Auto-adds `.NS` suffix (e.g., `RELIANCE.NS`, `TCS.NS`)
- **Sectors**: Technology, Finance, Healthcare, Energy, Consumer, Industrial, etc.

## ⚙️ Configuration

### Environment Variables

Key configuration options in `.env`:

```bash
# LLM Provider (groq recommended for free tier)
LLM_PROVIDER=groq
GROQ_API_KEY=your_key
GROQ_MODEL=llama-3.3-70b-versatile

# Redis
REDIS_URL=redis://localhost:6379

# Cache TTL (seconds)
CACHE_TTL_STOCKS=1800  # 30 minutes
CACHE_TTL_CHAT=300     # 5 minutes

# Rate Limiting
RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=3600  # per hour

# Optional: NewsAPI, Serper API
NEWSAPI_KEY=your_newsapi_key
SERPER_API_KEY=your_serper_key
```

See [.env.example](.env.example) for all options.

## 🧪 Testing

```bash
# Install test dependencies
uv pip install pytest httpx

# Run all tests (server must be running)
pytest tests/

# Run specific test module
pytest tests/test_health.py
pytest tests/test_crew_service.py   # no server needed
pytest tests/test_intent_classifier.py  # no server needed
```

## 📊 Project Structure

```
stocks_analyzer_be_01/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── chat.py           # Chat endpoint
│   │       ├── stocks.py         # Stock recommendations
│   │       ├── funds.py          # Fund recommendations
│   │       └── router.py         # Main router
│   ├── crew/
│   │   ├── agents.py             # 4 AI agents
│   │   ├── tasks.py              # Task definitions
│   │   └── tools/
│   │       ├── financial_data.py # yfinance tools
│   │       ├── market_research.py# Web search, news
│   │       └── sector_analysis.py# Sector performance
│   ├── models/
│   │   ├── requests.py           # Pydantic request models
│   │   └── responses.py          # Pydantic response models
│   ├── services/
│   │   ├── cache.py              # Redis caching
│   │   ├── crew_service.py       # CrewAI orchestration
│   │   └── job_store.py          # Job queue management
│   ├── utils/
│   │   ├── exceptions.py         # Custom exceptions
│   │   ├── logger.py             # JSON logging
│   │   └── validators.py         # Input validation
│   ├── config.py                 # Configuration settings
│   ├── dependencies.py           # FastAPI dependencies
│   └── main.py                   # FastAPI app entry point
├── tests/
│   ├── conftest.py               # Shared pytest fixtures
│   ├── test_health.py            # Health & root endpoint tests
│   ├── test_chat.py              # Chat endpoint tests
│   ├── test_stocks.py            # Stock recommendations tests
│   ├── test_funds.py             # Fund recommendations tests
│   ├── test_crew_service.py      # Agent & crew unit tests
│   └── test_intent_classifier.py # Intent classifier tests
├── docker-compose.yml            # Docker orchestration
├── Dockerfile                    # Docker build
├── pyproject.toml                # Python project config & dependencies
├── .env.example                  # Environment template
└── README.md                     # This file
```

## 🔧 Development

### Adding New Features

1. **New Endpoint**: Add to `app/api/v1/`
2. **New Agent**: Update `app/crew/agents.py`
3. **New Tool**: Add to `app/crew/tools/`
4. **New Model**: Update `app/models/`

### Code Quality

```bash
# Format code
ruff format .

# Lint code
ruff check .

# Type checking
mypy app/
```

## 🐛 Troubleshooting

### Common Issues

1. **Redis Connection Error**
   ```
   Solution: Ensure Redis is running on port 6379
   docker ps | grep redis
   ```

2. **Rate Limit Exceeded**
   ```
   Solution: Increase RATE_LIMIT_REQUESTS in .env
   ```

3. **LLM API Errors**
   ```
   Solution: Check API key validity and quota
   Test: curl https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY"
   ```

4. **Timeout on Stock Analysis**
   ```
   Solution: Increase CREW_TIMEOUT_SECONDS in .env
   ```

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [CrewAI](https://crewai.com/) - Multi-agent AI framework
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [yfinance](https://github.com/ranaroussi/yfinance) - Yahoo Finance market data
- [Groq](https://groq.com/) - Fast LLM inference

## 📞 Support

For issues, questions, or contributions, open a GitHub issue or refer to the [API Docs](http://localhost:8000/docs) once the server is running.

---

**Built with ❤️ using FastAPI, CrewAI, and Python**

