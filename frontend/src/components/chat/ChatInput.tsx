'use client'

import { useState, useRef } from 'react'
import { Send } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

interface ChatInputProps {
  onSubmit: (message: string, symbol: string) => void
  disabled: boolean
}

export function ChatInput({ onSubmit, disabled }: ChatInputProps) {
  const [message, setMessage] = useState('')
  const [symbol, setSymbol] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  function handleSubmit() {
    const trimmed = message.trim()
    if (!trimmed || disabled) return
    onSubmit(trimmed, symbol.trim().toUpperCase())
    setMessage('')
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="border-t border-slate-800 bg-slate-950 px-4 py-3">
      <div className="max-w-3xl mx-auto flex gap-2 items-end">
        <input
          type="text"
          placeholder="Ticker (e.g. AAPL)"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          maxLength={10}
          className="w-32 shrink-0 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-600 uppercase"
        />
        <Textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about a stock…"
          rows={1}
          disabled={disabled}
          className={cn(
            'flex-1 resize-none min-h-[40px] max-h-[100px] bg-slate-900 border-slate-700',
            'text-slate-200 placeholder-slate-500 focus-visible:ring-slate-600'
          )}
        />
        <Button
          onClick={handleSubmit}
          disabled={disabled || !message.trim()}
          size="icon"
          className="shrink-0 bg-slate-700 hover:bg-slate-600"
        >
          <Send size={16} />
        </Button>
      </div>
      <p className="max-w-3xl mx-auto mt-1 text-xs text-slate-600">
        Enter to send · Shift+Enter for new line
      </p>
    </div>
  )
}
