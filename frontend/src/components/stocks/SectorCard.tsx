import { Badge } from '@/components/ui/badge'
import { StockCard } from './StockCard'
import type { SectorRecommendation } from '@/lib/types'

export function SectorCard({ sector }: { sector: SectorRecommendation }) {
  const positive = sector.performance_percent >= 0
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <Badge variant="outline" className="border-slate-700 text-slate-400 text-xs">
          #{sector.rank}
        </Badge>
        <h3 className="font-semibold text-slate-100">{sector.sector}</h3>
        <span className={`text-sm font-medium ${positive ? 'text-green-400' : 'text-red-400'}`}>
          {positive ? '+' : ''}{sector.performance_percent.toFixed(2)}%
        </span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {sector.top_stocks.map((stock) => (
          <StockCard key={stock.symbol} stock={stock} />
        ))}
      </div>
    </div>
  )
}
