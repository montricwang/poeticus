import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type RefObject,
  type SetStateAction,
} from 'react'

import { poemContext, poemText } from '@/data/poem-library'
import type { Poem } from '@/data/poem-library'
import type { ChatTurn, ChatViewport } from '@/types/chat'
import type { SelectedText } from '@/types/poem'
import type { InitialChatState } from '@/lib/chat-initial-state'
import { buildHistory } from '@/lib/chat-history'
import { findRemoteConversation } from '@/lib/private-conversations'
import { loadServiceCapabilities } from '@/lib/service-capabilities'
import { createConversationId, loadPoemConversation } from '@/lib/chat-storage'
import { readChatStream, UsageLimitNotice } from '@/lib/chat-stream'
import { selectionForPython, validSelectionForPoem } from '@/lib/selection-offset'

function maxTurnId(turns: ChatTurn[]): number {
  return turns.reduce((max, turn) => Math.max(max, turn.id), 0)
}

// 已保存的历史轮次不是新消息，恢复时直接显示，不重新播放入场动画。
function restoredAnimationIds(turns: ChatTurn[]): Set<string> {
  const ids = new Set<string>()
  for (const turn of turns) {
    ids.add(`user:${turn.id}`)
    ids.add(`assistant:${turn.id}:${turn.status === 'pending' ? 'pending' : 'answer'}`)
  }
  return ids
}

type ChatSessionOptions = {
  initialChatState: InitialChatState
  poemId: string | null
  activePoem: Poem | null
  accountId?: string | null
  getAuthToken?: () => Promise<string | null>
  selected: SelectedText | null
  setSelected: Dispatch<SetStateAction<SelectedText | null>>
  switchControllerRef: RefObject<AbortController | null>
}

/** 管理当前作品的多轮聊天、流式生成、重试、改问和会话恢复。 */
export function useChatSession({
  initialChatState,
  poemId,
  activePoem,
  accountId = null,
  getAuthToken,
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
  const seenAnimationsRef = useRef(restoredAnimationIds(initialChatState.turns))
  const chatViewportRef = useRef<ChatViewport>({ scrollTop: 0, atBottom: true })
  const [hasUnreadReply, setHasUnreadReply] = useState(false)
  const skipRemoteRestoreRef = useRef<string | null>(null)
  const [historyError, setHistoryError] = useState('')

  // 保持回调稳定，避免目录筛选时让阅读器重复监听选区事件。
  const handleReaderSelect = useCallback(
    (value: SelectedText) => {
      if (!inFlightRef.current && !switchControllerRef.current) {
        setSelected(value)
      }
    },
    [setSelected, switchControllerRef],
  )

  /** 切换作品时恢复各自的草稿和历史，重置滚动及动画标记。 */
  function restoreForPoem(work: Poem) {
    skipRemoteRestoreRef.current = null
    setHistoryError('')
    const storedConversation = loadPoemConversation(work.id, accountId)
    const nextTurns = storedConversation?.turns ?? []
    setConversationId(storedConversation?.conversationId ?? createConversationId())
    setSelected(validSelectionForPoem(storedConversation?.draft.selection ?? null, poemText(work)))
    setQuestion(storedConversation?.draft.question ?? '')
    setTurns(nextTurns)
    nextTurnId.current = maxTurnId(nextTurns)
    setHasUnreadReply(false)
    seenAnimationsRef.current = restoredAnimationIds(nextTurns)
    chatViewportRef.current = { scrollTop: 0, atBottom: true }
  }

  // A signed-in reader with no local discussion can restore their latest
  // server-owned conversation for this poem on another device.
  useEffect(() => {
    if (
      !accountId ||
      !getAuthToken ||
      !poemId ||
      activePoem?.id !== poemId ||
      turns.length !== 0 ||
      inFlightRef.current ||
      skipRemoteRestoreRef.current === poemId
    )
      return

    let cancelled = false
    const previousConversationId = conversationId
    async function restoreRemote() {
      try {
        const token = await getAuthToken!()
        if (!token) return
        const snapshot = await findRemoteConversation(poemId!, token)
        if (cancelled || inFlightRef.current || !snapshot || snapshot.turns.length === 0) return
        // Keep a newly composed local message authoritative over a late response.
        setConversationId((current) =>
          current === previousConversationId ? snapshot.conversationId : current,
        )
        setTurns((current) => (current.length === 0 ? snapshot.turns : current))
        nextTurnId.current = maxTurnId(snapshot.turns)
        seenAnimationsRef.current = restoredAnimationIds(snapshot.turns)
      } catch {
        // Server failure must not discard the local draft or chat history.
      }
    }
    void restoreRemote()
    return () => {
      cancelled = true
    }
  }, [accountId, getAuthToken, poemId, activePoem?.id, conversationId, turns.length])

  /** 发起一次 SSE 生成，按 token 更新对应轮次并区分正常生成和重新生成。 */
  async function requestReply(
    turn: ChatTurn,
    regenerate = false,
    requestedConversationId = conversationId,
  ) {
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

    // --- 请求前构造当前作品上下文与受限对话历史 ---
    try {
      const capabilities = await loadServiceCapabilities()
      const history = buildHistory(turns, turn.id, capabilities.chat.maxHistoryTurns)

      // A missing/expired signed-in token must never fall back to anonymous chat.
      const token = accountId ? await getAuthToken?.() : null
      if (accountId && !token) throw new Error('登录凭证已失效，请重新登录')
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: 'Bearer ' + token } : {}),
        },
        body: JSON.stringify({
          poem,
          question: turn.question,
          selection: selectionForPython(turn.selection, poem),
          context: poemContext(activePoem),
          history,
          conversation_id: requestedConversationId,
          turn_number: turn.id,
        }),
      })

      // --- 流式更新本轮可见正文（重新生成时先保留旧答案）---
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
      // --- 按请求类型保留已收到的内容和失败信息 ---
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

  /** Start a genuinely new conversation without importing anonymous or old data. */
  function handleNewDiscussion() {
    if (inFlightRef.current || !poemId) return
    skipRemoteRestoreRef.current = poemId
    setConversationId(createConversationId())
    setTurns([])
    setQuestion('')
    setSelected(null)
    setHistoryError('')
    nextTurnId.current = 0
    seenAnimationsRef.current = new Set()
  }

  async function handleDeleteDiscussion() {
    if (!accountId || !getAuthToken || inFlightRef.current) return
    if (!window.confirm('删除当前云端讨论及其来源记忆？此操作无法撤销。')) return
    setHistoryError('')
    try {
      const token = await getAuthToken()
      if (!token) throw new Error('登录已失效')
      const response = await fetch('/api/conversations/' + encodeURIComponent(conversationId), {
        method: 'DELETE',
        headers: { Authorization: 'Bearer ' + token },
      })
      if (response.status !== 204 && response.status !== 404) {
        throw new Error('删除未完成，请重试')
      }
      handleNewDiscussion()
    } catch {
      setHistoryError('云端讨论未能删除，请重试')
    }
  }

  /** 新建对话轮次并发送当前草稿。 */
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

  /** 重试失败轮次，并丢弃它之后的历史。 */
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

  /** 重新生成已完成轮次，成功前保留旧答案。 */
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

  /** 修改某轮提问，从该轮重新开始对话。 */
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

    const nextConversationId = accountId ? createConversationId() : conversationId
    if (accountId) {
      skipRemoteRestoreRef.current = poemId
      setConversationId(nextConversationId)
    }
    setTurns([...turns.slice(0, index), editedTurn])
    void requestReply(editedTurn, false, nextConversationId)
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
    handleNewDiscussion,
    handleDeleteDiscussion,
    historyError,
  }
}
