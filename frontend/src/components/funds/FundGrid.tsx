import { Badge } from '@/components/ui/badge'
import { FundCard } from './FundCard'
import type { FundSectorRecommendation } from '@/lib/types'

export function FundGrid({ sectors }: { sectors: FundSectorRecommendation[] }) {
  return (
    <div className="space-y-8">
      {sectors.map((sector) => {
        const pos = sector.performance_percent >= 0
        return (
          <div key={sector.sector} className="space-y-3">
            <div className="flex items-center gap-3">
              <Badge variant="outline" className="border-slate-700 text-slate-400 text-xs">#{sector.rank}</Badge>
              <h3 className="font-semibold text-slate-100">{sector.sector}</h3>
              <span className={`text-sm font-medium ${pos ? 'text-green-400' : 'text-red-400'}`}>
                {pos ? '+' : ''}{sector.performance_percent.toFixed(2)}%
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {sector.top_funds.map((fund) => <FundCard key={fund.symbol} fund={fund} />)}
            </div>
          </div>
        )
      })}
    </div>
  )
}
