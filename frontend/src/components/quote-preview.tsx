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
 * Retain the last quote until its exit transition has finished.
 * Otherwise a conditional {selected && ...} unmounts the quote immediately.
 */
export function QuotePreview({ selected, loading, onClearQuote }: QuotePreviewProps) {
  const [rendered, setRendered] = useState<SelectedText | null>(selected)
  const [expanded, setExpanded] = useState(false)
  const contentRef = useRef<HTMLDivElement>(null)
  const [contentHeight, setContentHeight] = useState(0)

  // Measure the quote's natural height while its animated outer wrapper clips it.
  // A new selection only changes this height; it never remounts the preview.
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
      // Commit the new quote in one frame, then allow the next frame to expand it.
      // React can paint the collapsed grid row before its transition starts.
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
          <div className="flex min-w-0 items-start gap-2 border-l-2 border-violet-400/60 pl-3">
            <p
              className="poeticus-scrollport max-h-20 min-w-0 flex-1 overflow-y-auto whitespace-pre-wrap font-serif text-sm font-medium leading-6 text-foreground/85"
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
