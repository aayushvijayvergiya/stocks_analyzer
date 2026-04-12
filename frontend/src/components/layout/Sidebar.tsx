'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { MessageSquare, TrendingUp, Briefcase } from 'lucide-react'
import { cn } from '@/lib/utils'

const links = [
  { href: '/', label: 'Chat', icon: MessageSquare },
  { href: '/stocks', label: 'Stocks', icon: TrendingUp },
  { href: '/funds', label: 'Funds', icon: Briefcase },
]

export function Sidebar() {
  const pathname = usePathname()
  return (
    <aside className="w-48 shrink-0 flex flex-col border-r border-slate-800 bg-slate-950 py-4">
      <nav className="flex flex-col gap-1 px-2">
        {links.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
              pathname === href
                ? 'bg-slate-800 text-white'
                : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
            )}
          >
            <Icon size={16} />
            {label}
          </Link>
        ))}
      </nav>
    </aside>
  )
}
