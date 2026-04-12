'use client'
import { useState } from 'react'
import { ChevronDown, ChevronUp, TrendingUp, TrendingDown } from 'lucide-react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { FundRecommendation } from '@/lib/types'

function ScoreBadge({ score }: { score: number }) {
  const color = score >= 7 ? 'bg-green-900 text-green-300' : score >= 5 ? 'bg-amber-900 text-amber-300' : 'bg-red-900 text-red-300'
  return <span className={cn('text-xs font-semibold px-2 py-0.5 rounded-full', color)}>{score.toFixed(1)}</span>
}

export function FundCard({ fund }: { fund: FundRecommendation }) {
  const [expanded, setExpanded] = useState(false)
  const pos = (fund.change_percent ?? 0) >= 0
  return (
    <Card className="bg-slate-900 border-slate-800">
      <CardHeader className="pb-2 pt-4 px-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-bold text-slate-100">{fund.symbol}</p>
            <p className="text-xs text-slate-400 mt-0.5 truncate max-w-[130px]">{fund.name}</p>
          </div>
          <ScoreBadge score={fund.recommendation_score} />
        </div>
        <div className="flex items-center justify-between mt-2">
          <span className="text-sm font-medium text-slate-200">
            {fund.current_nav != null
              ? new Intl.NumberFormat('en-US', { style: 'currency', currency: fund.currency, minimumFractionDigits: 2 }).format(fund.current_nav)
              : 'N/A'}
          </span>
          <span className={cn('flex items-center gap-0.5 text-xs font-medium', pos ? 'text-green-400' : 'text-red-400')}>
            {pos ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
            {fund.change_percent != null ? `${pos ? '+' : ''}${fund.change_percent.toFixed(2)}%` : 'N/A'}
          </span>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <div className="flex gap-4 text-xs text-slate-400 mb-2">
          <span>Expense: <span className="text-slate-300">{fund.expense_ratio != null ? `${fund.expense_ratio}%` : 'N/A'}</span></span>
          <span>AUM: <span className="text-slate-300">{fund.aum ?? 'N/A'}</span></span>
        </div>
        <button onClick={() => setExpanded(v => !v)}
          className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition-colors">
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}{expanded ? 'Less' : 'Reasoning'}
        </button>
        {expanded && <p className="mt-2 text-xs text-slate-400 leading-relaxed">{fund.reasoning}</p>}
      </CardContent>
    </Card>
  )
}
