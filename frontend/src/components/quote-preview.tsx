import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { motionDurationMs } from '@/lib/motion'
import type { SelectedText } from '@/types/poem'

type QuotePreviewProps = {
  selected: SelectedText | null
  loading: boolean
  onClearQuote: () => void
}

/**
 * 移除引用时仍保留上一条引用，直到退出动画结束。
 * 若直接使用 {selected && ...}，清空选区会让引用立即卸载。
 */
export function QuotePreview({ selected, loading, onClearQuote }: QuotePreviewProps) {
  const [rendered, setRendered] = useState<SelectedText | null>(selected)
  const [expanded, setExpanded] = useState(false)
  const contentRef = useRef<HTMLDivElement>(null)
  const [contentHeight, setContentHeight] = useState(0)

  // 在外层动画容器裁剪内容时测量引用的自然高度；更换选区只更新高度，不重新挂载预览。
  useLayoutEffect(() => {
    const element = contentRef.current
    if (!element) return
    const measure = () => {
      const nextHeight = Math.ceil(element.getBoundingClientRect().height)
      setContentHeight((previous) => (previous === nextHeight ? previous : nextHeight))
    }
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    const frame = window.requestAnimationFrame(measure)
    return () => {
      window.cancelAnimationFrame(frame)
      observer.disconnect()
    }
  }, [])

  useEffect(() => {
    if (selected) {
      // 第一帧更新引用内容，下一帧再展开，让 React 有机会先绘制收起状态。
      let revealFrame: number | null = null
      const contentFrame = window.requestAnimationFrame(() => {
        setRendered(selected)
        revealFrame = window.requestAnimationFrame(() => setExpanded(true))
      })
      return () => {
        window.cancelAnimationFrame(contentFrame)
        if (revealFrame !== null) window.cancelAnimationFrame(revealFrame)
      }
    }

    const closeFrame = window.requestAnimationFrame(() => setExpanded(false))
    const timeout = window.setTimeout(
      () => setRendered(null),
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
        ? 0
        : motionDurationMs('--motion-quote-enter') + 20,
    )
    return () => {
      window.cancelAnimationFrame(closeFrame)
      window.clearTimeout(timeout)
    }
  }, [selected])

  return (
    <div
      aria-hidden={!expanded}
      style={{ height: expanded ? contentHeight : 0 }}
      className={
        'poeticus-quote-transition min-w-0 ' +
        (expanded ? 'poeticus-quote-open' : 'pointer-events-none')
      }
    >
      <div ref={contentRef} className="min-w-0" inert={!expanded}>
        {rendered && (
          <div className="inline-flex w-fit max-w-full min-w-0 items-start gap-1.5 border-l-2 border-editorial-red/60 pl-3">
            <p
              className="poeticus-scrollport max-h-20 min-w-0 flex-[0_1_auto] overflow-y-auto whitespace-pre-wrap font-serif text-sm font-medium leading-6 text-foreground/85"
              aria-label="引用原文"
            >
              {rendered.text}
            </p>
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              className="mt-0.5 shrink-0 rounded-sm text-muted-foreground"
              onClick={onClearQuote}
              disabled={loading || !expanded}
              aria-label="移除引用"
            >
              <X className="size-3.5" />
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
