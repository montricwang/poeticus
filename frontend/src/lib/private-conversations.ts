import type { ChatTurn } from '@/types/chat'
import type { ConversationSnapshot } from '@/lib/chat-storage'

type RemoteConversation = {
  id: string
  poem_id: string
  updated_at: string
}
type RemoteMessage = {
  turn_number: number
  role: 'user' | 'assistant'
  content: string
}
type RemoteDetail = {
  id: string
  poem_id: string
  messages: RemoteMessage[]
}

/** Server is authoritative for cross-device records. Never read another account's cache. */
export async function findRemoteConversation(
  poemId: string,
  token: string,
): Promise<ConversationSnapshot | null> {
  const headers = { Authorization: 'Bearer ' + token }
  const listing = await fetch('/api/conversations?limit=50', { headers, cache: 'no-store' })
  if (!listing.ok) throw new Error('无法读取云端讨论')
  const body: { conversations: RemoteConversation[] } = await listing.json()
  const newest = body.conversations.find((item) => item.poem_id === poemId)
  if (!newest) return null

  const response = await fetch('/api/conversations/' + encodeURIComponent(newest.id), {
    headers,
    cache: 'no-store',
  })
  if (!response.ok) throw new Error('无法恢复云端讨论')
  const detail: RemoteDetail = await response.json()
  if (detail.poem_id !== poemId || detail.id !== newest.id) {
    throw new Error('云端讨论的作品标识不匹配')
  }

  const byTurn = new Map<number, Partial<ChatTurn>>()
  for (const message of detail.messages) {
    if (!Number.isInteger(message.turn_number) || message.turn_number < 1) continue
    const turn = byTurn.get(message.turn_number) ?? {}
    if (message.role === 'user') turn.question = message.content
    if (message.role === 'assistant') turn.answer = message.content
    byTurn.set(message.turn_number, turn)
  }

  const turns: ChatTurn[] = [...byTurn.entries()]
    .sort(([a], [b]) => a - b)
    .filter(([, turn]) => typeof turn.question === 'string')
    .map(([id, turn]) => ({
      id,
      question: turn.question!,
      selection: null,
      answer: turn.answer ?? null,
      status: turn.answer ? 'done' : 'failed',
      error: turn.answer ? null : '此前生成未完成，请重新提问',
      usageLimitNotice: false,
      regenerating: false,
      regenerateError: null,
      regenerateLimitNotice: false,
      streamDraft: null,
    }))

  return {
    conversationId: detail.id,
    poemId,
    turns,
    draft: { question: '', selection: null },
    updatedAt: newest.updated_at,
  }
}
