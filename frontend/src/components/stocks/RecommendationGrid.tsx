import { SectorCard } from './SectorCard'
import type { SectorRecommendation } from '@/lib/types'

export function RecommendationGrid({ sectors }: { sectors: SectorRecommendation[] }) {
  return (
    <div className="space-y-8">
      {sectors.map((sector) => (
        <SectorCard key={sector.sector} sector={sector} />
      ))}
    </div>
  )
}
