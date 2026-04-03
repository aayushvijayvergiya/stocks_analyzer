'use client'

import { useState } from 'react'
import { ChevronDown, ChevronUp, ExternalLink } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { ChatMessage } from '@/lib/types'

export function MessageBubble({ message }: { message: ChatMessage }) {
  const [showSources, setShowSources] = useState(false)
  const [showReasoning, setShowReasoning] = useState(false)
  const isUser = message.role === 'user'

  return (
    <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[80%] rounded-2xl px-4 py-3 text-sm',
          isUser
            ? 'bg-slate-700 text-slate-100 rounded-br-sm'
            : 'bg-slate-800 text-slate-200 rounded-bl-sm'
        )}
      >
        <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>

        {/* Sources */}
        {message.sources && message.sources.length > 0 && (
          <div className="mt-3 border-t border-slate-700 pt-2">
            <button
              onClick={() => setShowSources((v) => !v)}
              className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200 transition-colors"
            >
              {showSources ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              {message.sources.length} source{message.sources.length !== 1 ? 's' : ''}
            </button>
            {showSources && (
              <ul className="mt-2 flex flex-col gap-1">
                {message.sources.map((src, i) => (
                  <li key={i}>
                    <a
                      href={src.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 underline underline-offset-2"
                    >
                      <ExternalLink size={10} />
                      {src.title}
                      <span className="text-slate-500 no-underline">· {src.date}</span>
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {/* Agent Reasoning */}
        {message.agent_reasoning &&
          Object.values(message.agent_reasoning).some(Boolean) && (
            <div className="mt-2 border-t border-slate-700 pt-2">
              <button
                onClick={() => setShowReasoning((v) => !v)}
                className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200 transition-colors"
              >
                {showReasoning ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                Agent reasoning
              </button>
              {showReasoning && (
                <div className="mt-2 flex flex-col gap-2">
                  {Object.entries(message.agent_reasoning).map(([agent, text]) =>
                    text ? (
                      <div key={agent}>
                        <Badge variant="secondary" className="mb-1 text-xs capitalize">
                          {agent.replace('_', ' ')}
                        </Badge>
                        <p className="text-xs text-slate-400 leading-relaxed">{text}</p>
                      </div>
                    ) : null
                  )}
                </div>
              )}
            </div>
          )}
      </div>
    </div>
  )
}
