import { Check, Copy, LoaderCircle, RotateCcw } from 'lucide-react'

import { AssistantMarkdown } from '@/components/assistant-markdown'
import { Button } from '@/components/ui/button'
import type { ChatTurn } from '@/components/chat-types'

type CopyStatus = {
  key: string
  status: 'success' | 'error'
} | null

type AssistantMessageProps = {
  turn: ChatTurn
  loading: boolean
  copyStatus: CopyStatus
  onCopy: (content: string) => void
  onRetry: () => void
  onRegenerate: () => void
}

export function AssistantMessage({
  turn,
  loading,
  copyStatus,
  onCopy,
  onRetry,
  onRegenerate,
}: AssistantMessageProps) {
  const copyKey = `${turn.id}:assistant`
  const copySucceeded = copyStatus?.key === copyKey && copyStatus.status === 'success'
  const copyFailed = copyStatus?.key === copyKey && copyStatus.status === 'error'

  if (turn.status === 'pending') {
    return (
      <div role="status" className="space-y-2">
        <p className="text-xs font-medium tracking-wide text-muted-foreground">AI 伴读</p>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <LoaderCircle className="size-4 animate-spin" />
          正在思考……
        </div>
      </div>
    )
  }

  if (turn.status === 'failed') {
    const notice = turn.usageLimitNotice === true
    return (
      <div
        className={`space-y-2 border-l-2 py-1 pl-3 ${notice ? 'border-border' : 'border-destructive/40'}`}
      >
        <p className="text-xs font-medium tracking-wide text-muted-foreground">
          {notice ? 'AI 伴读 · 稍等一会儿' : 'AI 伴读 · 请求失败'}
        </p>
        {/* 网络中断后保留已经收到的正文，而不是清空历史输出。 */}
        {turn.answer && (
          <div className="mb-3 select-text">
            <AssistantMarkdown content={turn.answer} />
          </div>
        )}
        <p
          role={notice ? 'status' : 'alert'}
          className={`mb-3 text-sm leading-6 ${notice ? 'text-muted-foreground' : 'text-destructive'}`}
        >
          {!notice && (turn.answer ? '回答未完成：' : '请求失败：')}
          {turn.error ?? '消息发送失败'}
        </p>
        <Button type="button" variant="outline" size="sm" disabled={loading} onClick={onRetry}>
          <RotateCcw className="mr-2 size-4" />
          {notice ? '稍后再试' : '重新请求'}
        </Button>
      </div>
    )
  }

  if (!turn.answer) return null

  return (
    <div className="min-w-0 space-y-2" aria-label="AI 伴读回复">
      <div className="text-xs font-medium tracking-wide text-muted-foreground">AI 伴读</div>
      <div className="group min-w-0 select-text">
        <AssistantMarkdown content={turn.answer} />

        {turn.status === 'streaming' && (
          <div role="status" className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
            <LoaderCircle className="size-3 animate-spin" />
            正在生成……
          </div>
        )}

        {/* 完整回答才允许复制和重新生成；生成中仍可手动选择正文。 */}
        {turn.status === 'done' && (
          <div className="mt-2 flex items-center gap-2 opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100 [@media(hover:none)]:opacity-100">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-8 text-muted-foreground/60 hover:text-foreground"
              onClick={() => onCopy(turn.answer ?? '')}
              aria-label="复制 AI 回答"
              title="复制 AI 回答"
            >
              {copySucceeded ? <Check className="size-4" /> : <Copy className="size-4" />}
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-8 text-muted-foreground/60 hover:text-foreground"
              onClick={onRegenerate}
              disabled={loading || turn.regenerating}
              aria-label="重新生成 AI 回答"
              title="重新生成"
            >
              {turn.regenerating ? (
                <LoaderCircle className="size-4 animate-spin" />
              ) : (
                <RotateCcw className="size-4" />
              )}
            </Button>
            {copyFailed && (
              <span role="alert" className="text-xs text-destructive">
                复制失败，请手动选择文字复制
              </span>
            )}
          </div>
        )}

        {/* 重生成时，旧答案仍在上方；新版本逐步出现。 */}
        {turn.regenerating && (
          <div className="mt-3 rounded-xl border border-border/60 bg-muted/30 p-3">
            <div
              role="status"
              className="mb-2 flex items-center gap-2 text-xs text-muted-foreground"
            >
              <LoaderCircle className="size-3 animate-spin" />
              正在重新生成……
            </div>
            {turn.streamDraft && <AssistantMarkdown content={turn.streamDraft} />}
          </div>
        )}

        {turn.regenerateError && (
          <div
            role={turn.regenerateLimitNotice ? 'status' : 'alert'}
            className={`mt-2 text-xs ${turn.regenerateLimitNotice ? 'text-muted-foreground' : 'text-destructive'}`}
          >
            {turn.regenerateLimitNotice
              ? turn.regenerateError
              : `重新生成失败：${turn.regenerateError}。原答案已保留，可再次重新生成。`}
            {turn.streamDraft && (
              <details className="mt-2 rounded-lg border border-destructive/20 p-2">
                <summary className="cursor-pointer">查看未完成的新回答</summary>
                <div className="mt-2 text-foreground">
                  <AssistantMarkdown content={turn.streamDraft} />
                </div>
              </details>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
