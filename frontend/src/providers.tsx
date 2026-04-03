'use client'

import { Toaster } from 'sonner'
import { MarketProvider } from '@/context/MarketContext'

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <MarketProvider>
      {children}
      <Toaster theme="dark" position="bottom-right" />
    </MarketProvider>
  )
}
