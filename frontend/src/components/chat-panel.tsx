import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react'

import { Button } from '@/components/ui/button'
import { MessageEntrance } from '@/components/message-entrance'
import { UserMessage } from '@/components/user-message'
import { AssistantMessage } from '@/components/assistant-message'
import { ChatComposer } from '@/components/chat-composer'
import { ChatMessageList } from '@/components/chat-message-list'
import { HorizontalEditorialDivider } from '@/components/editorial-divider'
import { cn } from '@/lib/utils'
import type { SelectedText } from '@/types/poem'
import type { ChatTurn, ChatViewport } from '@/types/chat'

type ChatPanelProps = {
  poemId: string
  swapPhase: 'steady' | 'leaving' | 'arriving'
  selected: SelectedText | null
  question: string
  turns: ChatTurn[]
  loading: boolean
  seenAnimationsRef: RefObject<Set<string>>
  viewportRef: RefObject<ChatViewport>
  hasUnreadReply: boolean
  onClearUnreadReply: () => void
  onQuestionChange: (value: string) => void
  onClearQuote: () => void
  onSend: () => void
  onRetry: (id: number) => void
  onRegenerate: (id: number) => void
  onEdit: (id: number, nextQuestion: string) => void
  fillAvailableHeight?: boolean
  className?: string
}

export function ChatPanel({
  poemId,
  swapPhase,
  selected,
  question,
  turns,
  loading,
  seenAnimationsRef,
  viewportRef,
  hasUnreadReply,
  onClearUnreadReply,
  onQuestionChange,
  onClearQuote,
  onSend,
  onRetry,
  onRegenerate,
  onEdit,
  fillAvailableHeight = false,
  className,
}: ChatPanelProps) {
  const chatListRef = useRef<HTMLDivElement>(null)
  const sectionRef = useRef<HTMLElement>(null)
  const historyContentRef = useRef<HTMLDivElement>(null)
  const composerRef = useRef<HTMLDivElement>(null)
  const [historyHeight, setHistoryHeight] = useState(0)
  const previousPoemRef = useRef(poemId)
  const initializedRef = useRef(false)
  const [isAtBottom, setIsAtBottom] = useState(true)
  const [hasContentAbove, setHasContentAbove] = useState(false)

  const [copyStatus, setCopyStatus] = useState<{
    key: string
    status: 'success' | 'error'
  } | null>(null)
  const [editingTurnId, setEditingTurnId] = useState<number | null>(null)
  const [editDraft, setEditDraft] = useState('')

  // Keep the toolbar/composer mounted while only the message viewport grows
  // or shrinks. The measured height is capped at the visible companion budget.
  useLayoutEffect(() => {
    if (fillAvailableHeight) return
    const section = sectionRef.current
    const messages = historyContentRef.current
    const composer = composerRef.current
    const list = chatListRef.current
    if (!section || !messages || !composer || !list) return

    const measure = () => {
      const maxHeight = Number.parseFloat(window.getComputedStyle(section).maxHeight)
      const available = Number.isFinite(maxHeight)
        ? Math.max(0, maxHeight - composer.getBoundingClientRect().height - 12)
        : window.innerHeight / 2
      const target = turns.length === 0 ? 0 : Math.min(messages.scrollHeight + 16, available)
      setHistoryHeight((previous) => (Math.abs(previous - target) < 1 ? previous : target))
      if (viewportRef.current.atBottom) {
        window.requestAnimationFrame(() => {
          list.scrollTop = list.scrollHeight
        })
      }
    }
    const observer = new ResizeObserver(measure)
    observer.observe(messages)
    observer.observe(composer)
    observer.observe(section)
    window.addEventListener('resize', measure)
    measure()
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [fillAvailableHeight, turns.length, viewportRef])

  // On poem switches the same component preserves the input region, but resets
  // the saved scroll-position initialization for the newly restored conversation.
  useLayoutEffect(() => {
    if (previousPoemRef.current === poemId) return
    previousPoemRef.current = poemId
    initializedRef.current = false
  }, [poemId])

  async function handleCopy(key: string, content: string) {
    try {
      await navigator.clipboard.writeText(content)
      setCopyStatus({ key, status: 'success' })
    } catch {
      setCopyStatus({ key, status: 'error' })
    }
  }

  useEffect(() => {
    if (copyStatus?.status !== 'success') return

    const timer = window.setTimeout(() => setCopyStatus(null), 2000)
    return () => window.clearTimeout(timer)
  }, [copyStatus])

  // 首次挂载恢复阅读位置；后续只有在底部时才跟随新消息。
  useLayoutEffect(() => {
    const list = chatListRef.current
    if (!list) return

    if (!initializedRef.current) {
      initializedRef.current = true
      list.scrollTop = viewportRef.current.atBottom
        ? list.scrollHeight
        : viewportRef.current.scrollTop
    } else if (viewportRef.current.atBottom) {
      list.scrollTop = list.scrollHeight
    }

    // 在渲染完成后同步按钮状态，避免在 React 渲染期间读取 Ref。
    const frame = window.requestAnimationFrame(() => {
      const atBottom = list.scrollHeight - list.scrollTop - list.clientHeight <= 64
      viewportRef.current.scrollTop = list.scrollTop
      viewportRef.current.atBottom = atBottom
      setIsAtBottom(atBottom)
      setHasContentAbove(list.scrollTop > 8)
    })
    return () => window.cancelAnimationFrame(frame)
  }, [turns, viewportRef])

  function handleScroll(list: HTMLDivElement) {
    const distanceToBottom = list.scrollHeight - list.scrollTop - list.clientHeight
    const atBottom = distanceToBottom <= 64

    viewportRef.current.scrollTop = list.scrollTop
    viewportRef.current.atBottom = atBottom
    setIsAtBottom(atBottom)
    setHasContentAbove(list.scrollTop > 8)

    if (atBottom && hasUnreadReply) {
      onClearUnreadReply()
    }
  }

  function scrollToBottom() {
    const list = chatListRef.current
    if (!list) return

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    list.scrollTo({
      top: list.scrollHeight,
      behavior: reduceMotion ? 'auto' : 'smooth',
    })
    // 等 onScroll 确认真正到达底部后，才清除「新回复」提示。
  }

  function handleSendFromComposer() {
    if (!question.trim() || loading) return

    // 主动发送意味着开始看最新一轮，不再停留在历史消息处。
    viewportRef.current.atBottom = true
    setIsAtBottom(true)
    onClearUnreadReply()

    const list = chatListRef.current
    if (list) {
      list.scrollTop = list.scrollHeight
      viewportRef.current.scrollTop = list.scrollTop
      setHasContentAbove(list.scrollTop > 8)
    }

    onSend()
  }

  return (
    <section
      ref={sectionRef}
      aria-label="阅读讨论"
      className={cn(
        'flex min-h-0 min-w-0 flex-col bg-transparent',
        fillAvailableHeight
          ? 'flex-1'
          : 'max-h-[var(--companion-panel-max-height)] overflow-hidden',
        className,
      )}
    >
      <ChatMessageList
        fillAvailableHeight={fillAvailableHeight}
        hasMessages={turns.length > 0}
        height={historyHeight}
        scrollRef={chatListRef}
        contentRef={historyContentRef}
        onScroll={handleScroll}
        hasContentAbove={hasContentAbove}
        isAtBottom={isAtBottom}
        hasUnreadReply={hasUnreadReply}
        onScrollToBottom={scrollToBottom}
        swapPhase={swapPhase}
        >
          {turns.map((turn, index) => (
            <div key={turn.id} className="space-y-4">
              {index > 0 && <HorizontalEditorialDivider className="mb-6 w-12" />}
              <MessageEntrance
                animationId={`user:${turn.id}`}
                seenAnimationsRef={seenAnimationsRef}
              >
                <UserMessage
                  turn={turn}
                  editing={editingTurnId === turn.id}
                  draft={editDraft}
                  loading={loading}
                  copyStatus={copyStatus}
                  onDraftChange={setEditDraft}
                  onStartEdit={() => {
                    setEditingTurnId(turn.id)
                    setEditDraft(turn.question)
                  }}
                  onCancelEdit={() => {
                    setEditingTurnId(null)
                    setEditDraft('')
                  }}
                  onSaveEdit={() => {
                    const isOlderMessage = turn.id !== turns[turns.length - 1]?.id

                    if (
                      isOlderMessage &&
                      !window.confirm('保存后将移除这条消息之后的对话，是否继续？')
                    ) {
                      return
                    }

                    onEdit(turn.id, editDraft.trim())
                    setEditingTurnId(null)
                    setEditDraft('')
                  }}
                  onCopy={(content) => {
                    void handleCopy(`${turn.id}:user`, content)
                  }}
                />
              </MessageEntrance>

              <MessageEntrance
                key={`assistant:${turn.id}:${turn.status === 'pending' ? 'pending' : 'answer'}`}
                animationId={`assistant:${turn.id}:${turn.status === 'pending' ? 'pending' : 'answer'}`}
                seenAnimationsRef={seenAnimationsRef}
                enabled={turn.status !== 'failed'}
              >
                <AssistantMessage
                  turn={turn}
                  loading={loading}
                  copyStatus={copyStatus}
                  onCopy={(content) => {
                    void handleCopy(`${turn.id}:assistant`, content)
                  }}
                  onRetry={() => onRetry(turn.id)}
                  onRegenerate={() => onRegenerate(turn.id)}
                />
              </MessageEntrance>
            </div>
          ))}
      </ChatMessageList>

      {/* The divider follows the history's height transition in both directions. */}
      <div
        aria-hidden="true"
        className={
          'grid min-h-0 transition-[grid-template-rows,opacity,margin-top] duration-[var(--motion-chat-history-resize)] ease-[var(--motion-ease-settle)] motion-reduce:transition-none ' +
          (turns.length > 0
            ? 'mt-2 grid-rows-[1fr] opacity-100'
            : 'mt-0 grid-rows-[0fr] opacity-0')
        }
      >
        <div className="min-h-0 overflow-hidden">
          <HorizontalEditorialDivider className="w-full" />
        </div>
      </div>

      <div ref={composerRef} className="shrink-0">
        <ChatComposer
          selected={selected}
          question={question}
          loading={loading}
          onQuestionChange={onQuestionChange}
          onClearQuote={onClearQuote}
          onSend={handleSendFromComposer}
        />
      </div>
    </section>
  )
}
