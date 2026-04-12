import { MarketDropdown } from './MarketDropdown'

export function Header() {
  return (
    <header className="h-14 shrink-0 flex items-center justify-between border-b border-slate-800 bg-slate-950 px-4">
      <span className="font-semibold text-slate-100 tracking-tight">StocksAI</span>
      <MarketDropdown />
    </header>
  )
}
