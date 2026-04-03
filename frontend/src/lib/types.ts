// ─── Markets ─────────────────────────────────────────────────────────────────
export type Market = 'US' | 'IN'
export type Timeframe = '7d' | '30d' | '90d'
export type RiskProfile = 'conservative' | 'balanced' | 'aggressive'
export type FundType = 'equity' | 'debt' | 'balanced'
export type JobStatus = 'pending' | 'processing' | 'completed' | 'failed'

// ─── Chat ────────────────────────────────────────────────────────────────────
export interface Source {
  title: string
  url: string
  date: string
}

export interface AgentReasoning {
  market_researcher?: string
  data_analyst?: string
  sector_analyst?: string
  investment_advisor?: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  agent_reasoning?: AgentReasoning
}

export interface ChatResponse {
  response: string
  sources: Source[]
  agent_reasoning: AgentReasoning
  stock_symbol: string
  timestamp: string
}

// ─── Stocks ──────────────────────────────────────────────────────────────────
export interface KeyMetrics {
  market_cap: number
  pe_ratio: number
  dividend_yield: number
  volume: number
  eps: number
  debt_to_equity: number
  roe: number
  fifty_two_week_high: number
  fifty_two_week_low: number
}

export interface StockRecommendation {
  symbol: string
  company_name: string
  current_price: number
  currency: string
  change_percentage: number
  recommendation_score: number
  reasoning: string
  key_metrics: KeyMetrics
}

export interface SectorRecommendation {
  sector: string
  performance_percent: number
  rank: number
  region: string
  top_stocks: StockRecommendation[]
}

// ─── Funds ───────────────────────────────────────────────────────────────────
export interface FundRecommendation {
  symbol: string
  name: string
  current_nav: number
  currency: string
  expense_ratio: number
  aum: string
  change_percent: number
  recommendation_score: number
  reasoning: string
}

export interface FundSectorRecommendation {
  sector: string
  performance_percent: number
  rank: number
  market: string
  top_funds: FundRecommendation[]
}

// ─── Jobs ────────────────────────────────────────────────────────────────────
export interface JobResult<T> {
  job_id: string
  status: JobStatus
  result?: { top_sectors: T[] }
  error?: string
  progress?: string
  created_at: string
  completed_at?: string
}

// ─── API error ───────────────────────────────────────────────────────────────
export interface ApiError {
  detail: string
  error_code?: string
  retry_after?: number
}
