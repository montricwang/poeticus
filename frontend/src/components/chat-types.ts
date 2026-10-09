import type { SelectedText } from '@/components/poem-reader'

export type HistoryMessage = {
  role: 'user' | 'assistant'
  content: string
}

export type ChatTurn = {
  id: number
  question: string
  selection: SelectedText | null
  answer: string | null
  status: 'pending' | 'streaming' | 'done' | 'failed'
  error: string | null
  /** HTTP 429 属于正常用量提示，不显示为红色故障。 */
  usageLimitNotice?: boolean
  regenerating: boolean
  regenerateError: string | null
  regenerateLimitNotice?: boolean
  /** 重新生成期间保留旧 answer，新版本写到这里。 */
  streamDraft: string | null
}

export type ChatViewport = {
  scrollTop: number
  atBottom: boolean
}
