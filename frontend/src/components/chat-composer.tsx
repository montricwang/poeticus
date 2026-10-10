import { useCallback, useLayoutEffect, useRef, useState, type CSSProperties } from 'react'
import { ArrowUp, LoaderCircle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { QuotePreview } from '@/components/quote-preview'
import { composerWidthForLines } from '@/lib/composer-width'
import type { SelectedText } from '@/types/poem'

type ChatComposerProps = {
  selected: SelectedText | null
  question: string
  loading: boolean
  onQuestionChange: (value: string) => void
  onClearQuote: () => void
  onSend: () => void
}

export function ChatComposer({
  selected,
  question,
  loading,
  onQuestionChange,
  onClearQuote,
  onSend,
}: ChatComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [fades, setFades] = useState({ top: false, bottom: false })
  const [composerWidth, setComposerWidth] = useState(0)

  const updateFades = useCallback((element: HTMLTextAreaElement) => {
    const top = element.scrollTop > 4
    const bottom = element.scrollHeight - element.clientHeight - element.scrollTop > 4
    setFades((previous) =>
      previous.top === top && previous.bottom === bottom ? previous : { top, bottom },
    )
  }, [])

  useLayoutEffect(() => {
    const element = textareaRef.current
    if (!element) return
    const measure = () => {
      updateFades(element)
      const canvas = document.createElement('canvas')
      const context = canvas.getContext('2d')
      if (!context) return

      const computed = window.getComputedStyle(element)
      context.font = computed.font || `${computed.fontSize} ${computed.fontFamily}`
      const width = composerWidthForLines(question, (line) => context.measureText(line).width)
      setComposerWidth((previous) => (previous === width ? previous : width))
    }
    const frame = window.requestAnimationFrame(measure)
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => {
      window.cancelAnimationFrame(frame)
      observer.disconnect()
    }
  }, [question, updateFades])

  return (
    <div className="shrink-0 bg-transparent px-0 pt-2 pb-0 lg:pt-2 lg:pb-1">
      <QuotePreview selected={selected} loading={loading} onClearQuote={onClearQuote} />

      <div
        className="poeticus-composer-frame bg-transparent py-1"
        style={{ '--composer-content-width': `${composerWidth}px` } as CSSProperties}
      >
        <Textarea
          ref={textareaRef}
          placeholder="针对诗句提出你的问题……"
          onScroll={(event) => updateFades(event.currentTarget)}
          aria-label="输入问题"
          aria-busy={loading}
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          onKeyDown={(event) => {
            // Shift + Enter 换行；中文输入法选字时不误发送。
            if (event.key !== 'Enter' || event.shiftKey) return
            if (event.nativeEvent.isComposing || event.keyCode === 229) {
              return
            }

            event.preventDefault()
            if (!loading && question.trim()) onSend()
          }}
          // readOnly 而非 disabled：生成中仍可滚动、选中文字，
          // 不再显示全局 Textarea 的禁止操作光标。
          readOnly={loading}
          className={
            'poeticus-scrollport min-h-16 max-h-24 overflow-y-auto overscroll-contain resize-none border-0 bg-transparent px-2 text-base leading-7 shadow-none focus-visible:ring-0 md:min-h-16 md:max-h-36 md:text-base dark:bg-transparent ' +
            (fades.top ? 'poeticus-input-fade-top ' : '') +
            (fades.bottom ? 'poeticus-input-fade-bottom' : '')
          }
        />

        <div className="flex items-center justify-between px-2">
          <span className="text-xs text-muted-foreground">
            {loading ? 'AI 正在回复' : 'Enter 发送 · Shift+Enter 换行'}
          </span>

          <Button
            type="button"
            size="icon"
            className="rounded-md"
            onClick={onSend}
            disabled={loading || !question.trim()}
            aria-label="发送消息"
          >
            {loading ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : (
              <ArrowUp className="size-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}
