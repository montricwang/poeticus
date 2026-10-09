import {
  useCallback,
  useRef,
  useState,
  type Dispatch,
  type RefObject,
  type SetStateAction,
} from 'react'

import { poemContext, poemText } from '@/data/poem-library'
import type { Poem } from '@/data/poem-library'
import type { ChatTurn, ChatViewport } from '@/components/chat-types'
import type { SelectedText } from '@/components/poem-reader'
import type { InitialChatState } from '@/lib/chat-initial-state'
import { buildHistory } from '@/lib/chat-history'
import { loadServiceCapabilities } from '@/lib/service-capabilities'
import { createConversationId, loadPoemConversation } from '@/lib/chat-storage'
import { readChatStream, UsageLimitNotice } from '@/lib/chat-stream'
import { selectionForPython, validSelectionForPoem } from '@/lib/selection-offset'

function maxTurnId(turns: ChatTurn[]): number {
  return turns.reduce((max, turn) => Math.max(max, turn.id), 0)
}

type ChatSessionOptions = {
  initialChatState: InitialChatState
  poemId: string | null
  activePoem: Poem | null
  selected: SelectedText | null
  setSelected: Dispatch<SetStateAction<SelectedText | null>>
  switchControllerRef: RefObject<AbortController | null>
}

export function useChatSession({
  initialChatState,
  poemId,
  activePoem,
  selected,
  setSelected,
  switchControllerRef,
}: ChatSessionOptions) {
  const poem = activePoem ? poemText(activePoem) : ''
  const [conversationId, setConversationId] = useState(initialChatState.conversationId)
  const [question, setQuestion] = useState(initialChatState.question)
  const [turns, setTurns] = useState<ChatTurn[]>(initialChatState.turns)
  const [chatLoading, setChatLoading] = useState(false)
  const inFlightRef = useRef(false)
  const nextTurnId = useRef(maxTurnId(initialChatState.turns))
  const seenAnimationsRef = useRef(new Set<string>())
  const chatViewportRef = useRef<ChatViewport>({ scrollTop: 0, atBottom: true })
  const [hasUnreadReply, setHasUnreadReply] = useState(false)

  // 保持回调稳定，避免目录筛选时让阅读器重复监听选区事件。
  const handleReaderSelect = useCallback(
    (value: SelectedText) => {
      if (!inFlightRef.current && !switchControllerRef.current) {
        setSelected(value)
      }
    },
    [setSelected, switchControllerRef],
  )

  function restoreForPoem(work: Poem) {
    const storedConversation = loadPoemConversation(work.id)
    const nextTurns = storedConversation?.turns ?? []
    setConversationId(storedConversation?.conversationId ?? createConversationId())
    setSelected(validSelectionForPoem(storedConversation?.draft.selection ?? null, poemText(work)))
    setQuestion(storedConversation?.draft.question ?? '')
    setTurns(nextTurns)
    nextTurnId.current = maxTurnId(nextTurns)
    setHasUnreadReply(false)
    seenAnimationsRef.current.clear()
    chatViewportRef.current = { scrollTop: 0, atBottom: true }
  }

  async function requestReply(turn: ChatTurn, regenerate = false) {
    if (
      inFlightRef.current ||
      switchControllerRef.current ||
      !activePoem ||
      activePoem.id !== poemId
    )
      return

    inFlightRef.current = true
    setChatLoading(true)
    let received = ''

    setTurns((previous) =>
      previous.map((item) => {
        if (item.id !== turn.id) return item
        if (regenerate) {
          // 原回答继续留在 answer，增量的新回答单独保存在 streamDraft。
          return {
            ...item,
            regenerating: true,
            regenerateError: null,
            regenerateLimitNotice: false,
            streamDraft: '',
          }
        }
        // 普通发送 / 失败重试开始的是一次新的完整生成。
        return {
          ...item,
          answer: null,
          status: 'pending',
          error: null,
          usageLimitNotice: false,
          regenerating: false,
          regenerateError: null,
          regenerateLimitNotice: false,
          streamDraft: null,
        }
      }),
    )

    try {
      const capabilities = await loadServiceCapabilities()
      const history = buildHistory(turns, turn.id, capabilities.chat.maxHistoryTurns)

      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          poem,
          question: turn.question,
          selection: selectionForPython(turn.selection, poem),
          context: poemContext(activePoem),
          history,
        }),
      })

      await readChatStream(response, (token) => {
        received += token
        setTurns((previous) =>
          previous.map((item) => {
            if (item.id !== turn.id) return item
            return regenerate
              ? { ...item, streamDraft: received }
              : { ...item, answer: received, status: 'streaming' }
          }),
        )
      })

      if (!received.trim()) {
        throw new Error('AI 返回了空回答')
      }

      // 用户阅读旧消息期间不强制跳底部；仅在完成时标记新回复。
      if (!chatViewportRef.current.atBottom) {
        setHasUnreadReply(true)
      }
      setTurns((previous) =>
        previous.map((item) =>
          item.id === turn.id
            ? {
                ...item,
                answer: received,
                streamDraft: null,
                status: 'done',
                error: null,
                usageLimitNotice: false,
                regenerating: false,
                regenerateError: null,
                regenerateLimitNotice: false,
              }
            : item,
        ),
      )
    } catch (error) {
      const message = error instanceof Error ? error.message : '消息发送失败'
      setTurns((previous) =>
        previous.map((item) => {
          if (item.id !== turn.id) return item
          if (regenerate) {
            // 保留原回答，也保留已经收到的新版本片段。
            return {
              ...item,
              regenerating: false,
              regenerateError: message,
              regenerateLimitNotice: error instanceof UsageLimitNotice,
              streamDraft: received || null,
            }
          }
          return {
            ...item,
            answer: received || null,
            status: 'failed',
            error: message,
            usageLimitNotice: error instanceof UsageLimitNotice,
            streamDraft: null,
            regenerating: false,
          }
        }),
      )
    } finally {
      inFlightRef.current = false
      setChatLoading(false)
    }
  }

  function handleSend() {
    if (!question.trim() || inFlightRef.current || switchControllerRef.current || !activePoem)
      return

    const turn: ChatTurn = {
      id: ++nextTurnId.current,
      question: question.trim(),
      selection: selected,
      answer: null,
      status: 'pending',
      error: null,
      usageLimitNotice: false,
      regenerating: false,
      regenerateError: null,
      regenerateLimitNotice: false,
      streamDraft: null,
    }

    setTurns((previous) => [...previous, turn])
    setQuestion('')
    setSelected(null)

    void requestReply(turn)
  }

  function handleRetry(id: number) {
    if (inFlightRef.current) return

    const index = turns.findIndex((item) => item.id === id)
    if (index === -1) return

    const turn = turns[index]
    if (turn.status !== 'failed') return

    // 重试旧轮次会改变过去，因此丢弃它之后的对话。
    setTurns(turns.slice(0, index + 1))
    void requestReply(turn)
  }

  function handleRegenerate(id: number) {
    if (inFlightRef.current) return

    const index = turns.findIndex((item) => item.id === id)
    if (index === -1) return

    const turn = turns[index]
    if (turn.status !== 'done' || !turn.answer || turn.regenerating) {
      return
    }

    // 重新生成旧轮次会改变过去，因此丢弃它之后的对话。
    setTurns(turns.slice(0, index + 1))
    void requestReply(turn, true)
  }

  function handleEdit(id: number, nextQuestion: string) {
    if (inFlightRef.current || !nextQuestion.trim()) return
    const index = turns.findIndex((item) => item.id === id)
    if (index === -1) return
    const turn = turns[index]

    seenAnimationsRef.current.delete(`assistant:${id}:answer`)
    const editedTurn: ChatTurn = {
      ...turn,
      question: nextQuestion.trim(),
      answer: null,
      status: 'pending',
      error: null,
      usageLimitNotice: false,
      regenerating: false,
      regenerateError: null,
      regenerateLimitNotice: false,
      streamDraft: null,
    }

    setTurns([...turns.slice(0, index), editedTurn])
    void requestReply(editedTurn)
  }

  return {
    conversationId,
    question,
    setQuestion,
    turns,
    chatLoading,
    inFlightRef,
    seenAnimationsRef,
    chatViewportRef,
    hasUnreadReply,
    setHasUnreadReply,
    handleReaderSelect,
    restoreForPoem,
    handleSend,
    handleRetry,
    handleRegenerate,
    handleEdit,
  }
}
