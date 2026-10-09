import { ArrowUp, LoaderCircle, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import type { SelectedText } from '@/types/poem'

type ChatComposerProps = {
  selected: SelectedText | null
  question: string
  loading: boolean
  onQuestionChange: (value: string) => void
  onClearQuote: () => void
  onSend: () => void
  showDivider?: boolean
}

export function ChatComposer({
  selected,
  question,
  loading,
  onQuestionChange,
  onClearQuote,
  onSend,
  showDivider = true,
}: ChatComposerProps) {
  return (
    <div className="shrink-0 bg-transparent px-0 pt-3 pb-0 lg:py-4">
      {showDivider && <div className="mx-2 mb-3 h-px bg-border/60" aria-hidden="true" />}

      {/* 划词引用只保留旁引竖线与关闭按钮，不再占一整行显示“引用原文”。 */}
      {selected && (
        <div className="mb-2 flex min-w-0 items-start gap-2 border-l-2 border-violet-400/60 pl-3">
          <p
            className="max-h-20 min-w-0 flex-1 overflow-y-auto whitespace-pre-wrap font-serif text-sm leading-6 text-foreground/80"
            aria-label="引用原文"
          >
            {selected.text}
          </p>
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            className="mt-0.5 shrink-0 rounded-sm text-muted-foreground"
            onClick={onClearQuote}
            disabled={loading}
            aria-label="移除引用"
          >
            <X className="size-3.5" />
          </Button>
        </div>
      )}

      <div className="bg-transparent py-1">
        <Textarea
          placeholder="针对诗句提出你的问题……"
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
          className="min-h-16 max-h-24 overflow-y-auto overscroll-contain resize-none border-0 bg-transparent px-2 leading-6 shadow-none focus-visible:ring-0 md:min-h-24 md:max-h-36 dark:bg-transparent"
        />

        <div className="flex items-center justify-between px-2">
          <span className="text-xs text-muted-foreground">
            {loading ? 'AI 正在回复' : 'Enter 发送 · Shift+Enter 换行'}
          </span>

          <Button
            type="button"
            size="icon"
            className="rounded-xl"
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
