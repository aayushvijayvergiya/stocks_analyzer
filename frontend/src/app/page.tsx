'use client'

import { ChatWindow } from '@/components/chat/ChatWindow'
import { ChatInput } from '@/components/chat/ChatInput'
import { useChat } from '@/hooks/useChat'
import { useMarket } from '@/context/MarketContext'

export default function ChatPage() {
  const { messages, loading, submit } = useChat()
  const { market } = useMarket()

  return (
    <div className="flex flex-col h-full">
      <ChatWindow messages={messages} loading={loading} />
      <ChatInput
        onSubmit={(message, symbol) => submit(message, symbol, market)}
        disabled={loading}
      />
    </div>
  )
}
