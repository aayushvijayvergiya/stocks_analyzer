'use client'

import { createContext, useContext, useState } from 'react'
import type { Market } from '@/lib/types'

interface MarketContextValue {
  market: Market
  setMarket: (m: Market) => void
}

const MarketContext = createContext<MarketContextValue>({
  market: 'US',
  setMarket: () => {},
})

export function MarketProvider({ children }: { children: React.ReactNode }) {
  const [market, setMarket] = useState<Market>('US')
  return (
    <MarketContext.Provider value={{ market, setMarket }}>
      {children}
    </MarketContext.Provider>
  )
}

export function useMarket() {
  return useContext(MarketContext)
}
