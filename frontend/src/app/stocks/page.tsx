'use client'
import { useState, useCallback } from 'react'
import { Loader2, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { RecommendationGrid } from '@/components/stocks/RecommendationGrid'
import { useJob } from '@/hooks/useJob'
import { useMarket } from '@/context/MarketContext'
import { postStockRecommendations, getStockJob } from '@/lib/api'
import { cn } from '@/lib/utils'
import type { Timeframe, RiskProfile, SectorRecommendation } from '@/lib/types'

const timeframes: Timeframe[] = ['7d', '30d', '90d']
const riskProfiles: { value: RiskProfile; label: string }[] = [
  { value: 'conservative', label: 'Conservative' },
  { value: 'balanced', label: 'Balanced' },
  { value: 'aggressive', label: 'Aggressive' },
]

export default function StocksPage() {
  const { market } = useMarket()
  const [timeframe, setTimeframe] = useState<Timeframe>('30d')
  const [risk, setRisk] = useState<RiskProfile>('balanced')
  const [jobId, setJobId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const fetcher = useCallback((id: string) => getStockJob(id), [])
  const { status, progress, result, error } = useJob<SectorRecommendation>({ jobId, fetcher })

  async function runAnalysis() {
    setSubmitting(true)
    try {
      const { job_id } = await postStockRecommendations({ timeframe, market, risk_profile: risk })
      setJobId(job_id)
    } catch { /* toasted in api.ts */ } finally { setSubmitting(false) }
  }

  const isRunning = status === 'pending' || status === 'processing'

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-xl font-semibold text-slate-100 mb-6">Stock Recommendations</h1>
      <div className="flex flex-wrap gap-4 mb-6">
        <div>
          <p className="text-xs text-slate-500 mb-1.5">Timeframe</p>
          <div className="flex gap-1">
            {timeframes.map(t => (
              <button key={t} onClick={() => setTimeframe(t)}
                className={cn('px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
                  timeframe === t ? 'bg-slate-700 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200')}>{t}</button>
            ))}
          </div>
        </div>
        <div>
          <p className="text-xs text-slate-500 mb-1.5">Risk Profile</p>
          <div className="flex gap-1">
            {riskProfiles.map(({ value, label }) => (
              <button key={value} onClick={() => setRisk(value)}
                className={cn('px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
                  risk === value ? 'bg-slate-700 text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200')}>{label}</button>
            ))}
          </div>
        </div>
      </div>
      <Button onClick={runAnalysis} disabled={isRunning || submitting} className="mb-6 bg-slate-700 hover:bg-slate-600">
        {isRunning || submitting ? <><Loader2 size={14} className="mr-2 animate-spin" />Analyzing…</>
          : result ? <><RefreshCw size={14} className="mr-2" />Re-run Analysis</> : 'Run Analysis'}
      </Button>
      {isRunning && <p className="text-sm text-slate-400 mb-6">{progress ?? 'Starting analysis…'}</p>}
      {error && (
        <div className="mb-6 rounded-md border border-red-900 bg-red-950 px-4 py-3 text-sm text-red-300">
          {error}<button onClick={runAnalysis} className="ml-3 underline hover:text-red-200">Retry</button>
        </div>
      )}
      {result && <RecommendationGrid sectors={result.top_sectors} />}
    </div>
  )
}
