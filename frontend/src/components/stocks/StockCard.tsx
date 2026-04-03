'use client'

import { useState } from 'react'
import { ChevronDown, ChevronUp, TrendingUp, TrendingDown } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import type { StockRecommendation } from '@/lib/types'

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 7 ? 'bg-green-900 text-green-300' :
    score >= 5 ? 'bg-amber-900 text-amber-300' :
                 'bg-red-900 text-red-300'
  return (
    <span className={cn('text-xs font-semibold px-2 py-0.5 rounded-full', color)}>
      {score.toFixed(1)}
    </span>
  )
}

function fmt(n: number, decimals = 2) {
  return n?.toFixed(decimals) ?? '—'
}

function fmtCurrency(n: number, currency: string) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency, minimumFractionDigits: 2 }).format(n)
}

function fmtLargeNum(n: number) {
  if (n >= 1e12) return `${(n / 1e12).toFixed(2)}T`
  if (n >= 1e9)  return `${(n / 1e9).toFixed(2)}B`
  if (n >= 1e6)  return `${(n / 1e6).toFixed(2)}M`
  return String(n)
}

export function StockCard({ stock }: { stock: StockRecommendation }) {
  const [expanded, setExpanded] = useState(false)
  const positive = stock.change_percentage >= 0

  return (
    <Card className="bg-slate-900 border-slate-800">
      <CardHeader className="pb-2 pt-4 px-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-bold text-slate-100">{stock.symbol}</p>
            <p className="text-xs text-slate-400 mt-0.5 truncate max-w-[120px]">{stock.company_name}</p>
          </div>
          <ScoreBadge score={stock.recommendation_score} />
        </div>
        <div className="flex items-center justify-between mt-2">
          <span className="text-sm font-medium text-slate-200">
            {fmtCurrency(stock.current_price, stock.currency)}
          </span>
          <span className={cn('flex items-center gap-0.5 text-xs font-medium', positive ? 'text-green-400' : 'text-red-400')}>
            {positive ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
            {positive ? '+' : ''}{fmt(stock.change_percentage)}%
          </span>
        </div>
      </CardHeader>

      <CardContent className="px-4 pb-4">
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition-colors"
        >
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          {expanded ? 'Less' : 'Details'}
        </button>

        {expanded && (
          <div className="mt-3 space-y-3">
            <table className="w-full text-xs text-slate-400">
              <tbody className="divide-y divide-slate-800">
                {[
                  ['Market Cap', fmtLargeNum(stock.key_metrics.market_cap)],
                  ['P/E Ratio', fmt(stock.key_metrics.pe_ratio)],
                  ['EPS', fmt(stock.key_metrics.eps)],
                  ['ROE', `${fmt(stock.key_metrics.roe)}%`],
                  ['D/E Ratio', fmt(stock.key_metrics.debt_to_equity)],
                  ['Dividend Yield', `${fmt(stock.key_metrics.dividend_yield)}%`],
                  ['52W High', fmtCurrency(stock.key_metrics.fifty_two_week_high, stock.currency)],
                  ['52W Low', fmtCurrency(stock.key_metrics.fifty_two_week_low, stock.currency)],
                ].map(([label, value]) => (
                  <tr key={label} className="py-1">
                    <td className="py-1 text-slate-500">{label}</td>
                    <td className="py-1 text-right text-slate-300 font-medium">{value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-xs text-slate-400 leading-relaxed">{stock.reasoning}</p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
