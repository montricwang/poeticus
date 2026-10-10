import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react'
import { ArrowDown } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { MessageEntrance } from '@/components/message-entrance'
import { UserMessage } from '@/components/user-message'
import { AssistantMessage } from '@/components/assistant-message'
import { ChatComposer } from '@/components/chat-composer'
import { HorizontalEditorialDivider } from '@/components/editorial-divider'
import { cn } from '@/lib/utils'
import type { SelectedText } from '@/types/poem'
import type { ChatTurn, ChatViewport } from '@/types/chat'

type ChatPanelProps = {
  poemId: string
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

    const history = historyContentRef.current
    if (history && turns.length > 0) {
      // Saved turns appear together; only their content fades, not the whole pane.
      history.classList.remove('poeticus-chat-content-enter')
      void history.offsetWidth
      history.classList.add('poeticus-chat-content-enter')
    }
  }, [poemId, turns.length])

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
      {/* 全屏移动工作区没有消息时，用弹性空白把输入区压到底部；
          第一轮消息出现后，这一块自然替换成唯一的聊天滚动区。 */}
      {fillAvailableHeight && turns.length === 0 && (
        <div className="min-h-0 flex-1" aria-hidden="true" />
      )}

      {(turns.length > 0 || !fillAvailableHeight) && (
        <div
          className={cn(
            'relative min-h-0',
            fillAvailableHeight
              ? 'flex flex-1'
              : 'shrink-0 overflow-hidden transition-[height] duration-[var(--motion-chat-history-resize)] ease-[var(--motion-ease-settle)] motion-reduce:transition-none',
          )}
          style={fillAvailableHeight ? undefined : { height: historyHeight }}
        >
          <div
            ref={chatListRef}
            onScroll={(event) => handleScroll(event.currentTarget)}
            className={cn(
              'poeticus-scrollport flex h-full min-h-0 w-full flex-1 flex-col overflow-y-auto overscroll-contain pt-3 pb-1 pr-2',
              hasContentAbove && 'poeticus-scroll-fade-top',
            )}
          >
            <div ref={historyContentRef} className="flex flex-col gap-6">
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
            </div>
          </div>

          <div
            className="pointer-events-none absolute right-2 bottom-0 left-0 h-8 bg-[linear-gradient(to_bottom,transparent_0%,color-mix(in_oklab,var(--background)_72%,transparent)_62%,var(--background)_100%)] dark:h-6 dark:bg-[linear-gradient(to_bottom,transparent_0%,color-mix(in_oklab,var(--background)_48%,transparent)_68%,var(--background)_100%)]"
            aria-hidden="true"
          />

          {!isAtBottom && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="absolute bottom-4 left-1/2 z-10 -translate-x-1/2 rounded-md bg-background/95 shadow-md backdrop-blur-sm"
              aria-label={hasUnreadReply ? '新回复已生成，滚动到底部' : '滚动到底部'}
              onClick={scrollToBottom}
            >
              <ArrowDown className="size-4" />
              {hasUnreadReply && (
                <>
                  <span className="size-1.5 rounded-full bg-violet-500" />
                  <span>新回复</span>
                </>
              )}
            </Button>
          )}
        </div>
      )}

      {/* 横向分割线由讨论父容器管理，不占用输入组件内部空间。 */}
      {turns.length > 0 && <HorizontalEditorialDivider className="mt-2 w-full" />}

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
