'use client'

import { useMarket } from '@/context/MarketContext'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

export function MarketDropdown() {
  const { market, setMarket } = useMarket()
  return (
    <Select value={market} onValueChange={(v) => setMarket(v as 'US' | 'IN')}>
      <SelectTrigger className="w-24 bg-transparent border-slate-700 text-slate-200 text-sm">
        <SelectValue />
      </SelectTrigger>
      <SelectContent className="bg-slate-900 border-slate-700">
        <SelectItem value="US" className="text-slate-200 focus:bg-slate-800">🇺🇸 US</SelectItem>
        <SelectItem value="IN" className="text-slate-200 focus:bg-slate-800">🇮🇳 India</SelectItem>
      </SelectContent>
    </Select>
  )
}
