import type { ReactNode, RefObject } from 'react'
import { ArrowDown } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type ChatMessageListProps = {
  children: ReactNode
  fillAvailableHeight: boolean
  hasMessages: boolean
  height: number
  scrollRef: RefObject<HTMLDivElement | null>
  contentRef: RefObject<HTMLDivElement | null>
  onScroll: (element: HTMLDivElement) => void
  hasContentAbove: boolean
  isAtBottom: boolean
  hasUnreadReply: boolean
  onScrollToBottom: () => void
  swapPhase: 'steady' | 'leaving' | 'arriving'
}

/** Owns the scrolling, content fade and bottom-edge affordances, not the composer. */
export function ChatMessageList({
  children,
  fillAvailableHeight,
  hasMessages,
  height,
  scrollRef,
  contentRef,
  onScroll,
  hasContentAbove,
  isAtBottom,
  hasUnreadReply,
  onScrollToBottom,
  swapPhase,
}: ChatMessageListProps) {
  return (
    <div
      className={cn(
        'relative min-h-0',
        fillAvailableHeight
          ? 'flex flex-1'
          : 'shrink-0 overflow-hidden transition-[height] duration-[var(--motion-chat-history-resize)] ease-[var(--motion-ease-settle)] motion-reduce:transition-none',
      )}
      style={fillAvailableHeight ? undefined : { height }}
    >
      <div
        ref={scrollRef}
        onScroll={(event) => onScroll(event.currentTarget)}
        className={cn(
          'poeticus-scrollport flex h-full min-h-0 w-full flex-1 flex-col overflow-y-auto overscroll-contain pt-3 pb-1 pr-2',
          hasContentAbove && 'poeticus-scroll-fade-top',
        )}
      >
        <div
          ref={contentRef}
          className={
            'flex flex-col gap-6 transition-opacity ease-[var(--motion-ease-settle)] motion-reduce:transition-none ' +
            (swapPhase === 'steady'
              ? 'opacity-100 duration-[var(--motion-chat-content-enter)]'
              : 'opacity-0 duration-[var(--motion-poem-swap)]')
          }
        >
          {children}
        </div>
      </div>

      {hasMessages && (
        <div
          className="pointer-events-none absolute right-2 bottom-0 left-0 h-8 bg-[linear-gradient(to_bottom,transparent_0%,color-mix(in_oklab,var(--background)_72%,transparent)_62%,var(--background)_100%)] dark:h-6 dark:bg-[linear-gradient(to_bottom,transparent_0%,color-mix(in_oklab,var(--background)_48%,transparent)_68%,var(--background)_100%)]"
          aria-hidden="true"
        />
      )}

      {hasMessages && !isAtBottom && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="absolute bottom-4 left-1/2 z-10 -translate-x-1/2 rounded-md bg-background/95 shadow-md backdrop-blur-sm"
          aria-label={hasUnreadReply ? '新回复已生成，滚动到底部' : '滚动到底部'}
          onClick={onScrollToBottom}
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
  )
}
