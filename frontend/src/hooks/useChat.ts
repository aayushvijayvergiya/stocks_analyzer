import { useState } from 'react'
import { toast } from 'sonner'
import { postChat } from '@/lib/api'
import type { ChatMessage, Market } from '@/lib/types'

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(false)

  async function submit(message: string, symbol: string, market: Market) {
    const userMsg: ChatMessage = { role: 'user', content: message }
    setMessages((prev) => [...prev, userMsg])
    setLoading(true)

    try {
      const res = await postChat({
        message,
        stock_symbol: symbol || undefined,
        market,
        context: messages.map((m) => ({ role: m.role, content: m.content })),
      })

      const assistantMsg: ChatMessage = {
        role: 'assistant',
        content: res.response,
        sources: res.sources,
        agent_reasoning: res.agent_reasoning,
      }
      setMessages((prev) => [...prev, assistantMsg])
    } catch (err: unknown) {
      const error = err as Error & { status?: number; retry_after?: number }
      if (error.status === 429) {
        toast.error(`Rate limited. Try again in ${error.retry_after ?? 60}s`)
      } else if (error.status === 503) {
        toast.error('Service temporarily unavailable')
      } else {
        toast.error('Could not reach server')
      }
      // Remove the optimistically added user message on error
      setMessages((prev) => prev.slice(0, -1))
    } finally {
      setLoading(false)
    }
  }

  return { messages, loading, submit }
}
