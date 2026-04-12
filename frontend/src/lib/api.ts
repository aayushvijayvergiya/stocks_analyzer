import type {
  ChatResponse,
  JobResult,
  Market,
  RiskProfile,
  SectorRecommendation,
  FundSectorRecommendation,
  FundType,
  Timeframe,
  ApiError,
} from './types'

const BASE = 'http://localhost:8000/api/v1'

function requestId() {
  return Math.random().toString(36).slice(2, 10)
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-Request-ID': requestId(),
      ...(init?.headers ?? {}),
    },
  })

  if (!res.ok) {
    const body: ApiError = await res.json().catch(() => ({ detail: res.statusText }))
    const err = new Error(body.detail ?? 'Request failed') as Error & { status: number; retry_after?: number }
    err.status = res.status
    if (res.status === 429) {
      err.retry_after = body.retry_after
    }
    throw err
  }

  return res.json() as Promise<T>
}

// ─── Chat ────────────────────────────────────────────────────────────────────
export interface PostChatParams {
  message: string
  stock_symbol?: string
  market?: Market
  context?: { role: string; content: string }[]
}

export function postChat(params: PostChatParams): Promise<ChatResponse> {
  return apiFetch('/chat', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

// ─── Stock Recommendations ────────────────────────────────────────────────────
export interface PostStockRecommendationsParams {
  timeframe: Timeframe
  market?: Market
  risk_profile?: RiskProfile
}

export function postStockRecommendations(
  params: PostStockRecommendationsParams
): Promise<{ job_id: string }> {
  return apiFetch('/stocks/recommendations', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

export function getStockJob(jobId: string): Promise<JobResult<SectorRecommendation>> {
  return apiFetch(`/stocks/recommendations/${jobId}`)
}

// ─── Fund Recommendations ─────────────────────────────────────────────────────
export interface PostFundRecommendationsParams {
  timeframe: Timeframe
  market?: Market
  risk_profile?: RiskProfile
  fund_type?: FundType
}

export function postFundRecommendations(
  params: PostFundRecommendationsParams
): Promise<{ job_id: string }> {
  return apiFetch('/funds/recommendations', {
    method: 'POST',
    body: JSON.stringify(params),
  })
}

export function getFundJob(jobId: string): Promise<JobResult<FundSectorRecommendation>> {
  return apiFetch(`/funds/recommendations/${jobId}`)
}
