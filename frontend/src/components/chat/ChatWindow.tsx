'use client'

import { useEffect, useRef } from 'react'
import { MessageBubble } from './MessageBubble'
import type { ChatMessage } from '@/lib/types'

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="bg-slate-800 rounded-2xl rounded-bl-sm px-4 py-3">
        <div className="flex gap-1 items-center h-4">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce"
              style={{ animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

interface ChatWindowProps {
  messages: ChatMessage[]
  loading: boolean
}

export function ChatWindow({ messages, loading }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <div className="max-w-3xl mx-auto flex flex-col gap-4">
        {messages.length === 0 && (
          <div className="flex justify-start">
            <div className="bg-slate-800 rounded-2xl rounded-bl-sm px-4 py-3 text-sm text-slate-300 max-w-[80%]">
              Ask me anything about a stock — price, news, outlook, metrics. Try:
              <ul className="mt-2 list-disc list-inside text-slate-400 flex flex-col gap-1">
                <li>&quot;What&apos;s the outlook for Apple?&quot;</li>
                <li>&quot;Latest news for RELIANCE&quot;</li>
                <li>&quot;Compare MSFT and GOOGL fundamentals&quot;</li>
              </ul>
            </div>
          </div>
        )}
        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}
        {loading && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
