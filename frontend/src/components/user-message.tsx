import { Check, Copy, Pencil } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ActionTooltip } from '@/components/action-tooltip'
import { Textarea } from '@/components/ui/textarea'
import { AssistantMarkdown } from '@/components/assistant-markdown'
import type { ChatTurn } from '@/types/chat'

type CopyStatus = {
  key: string
  status: 'success' | 'error'
} | null

type UserMessageProps = {
  turn: ChatTurn
  editing: boolean
  draft: string
  loading: boolean
  copyStatus: CopyStatus

  onDraftChange: (value: string) => void
  onStartEdit: () => void
  onCancelEdit: () => void
  onSaveEdit: () => void
  onCopy: (content: string) => void
}

export function UserMessage({
  turn,
  editing,
  draft,
  loading,
  copyStatus,
  onDraftChange,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onCopy,
}: UserMessageProps) {
  const copyKey = `${turn.id}:user`

  const copyContent = turn.selection
    ? `引用原文：${turn.selection.text}

问题：${turn.question}`
    : turn.question

  const copySucceeded = copyStatus?.key === copyKey && copyStatus.status === 'success'

  const copyFailed = copyStatus?.key === copyKey && copyStatus.status === 'error'

  return (
    <div className="group flex min-w-0 w-full flex-col items-start gap-2" aria-label="读者提问">
      <span className="text-xs font-medium tracking-wide text-muted-foreground">读者</span>
      <div className="flex min-w-0 w-full flex-col items-start gap-2">
        {editing ? (
          /* 编辑模式 */
          <div className="w-full min-w-64 space-y-3 rounded-sm bg-muted/45 p-3 dark:bg-muted/25">
            {turn.selection && (
              <div className="border-l-2 border-violet-400/70 py-1 pl-3 pr-1 text-base leading-7 text-muted-foreground">
                {turn.selection.text}
              </div>
            )}

            <Textarea
              autoFocus
              value={draft}
              onChange={(event) => onDraftChange(event.target.value)}
              className="poeticus-scrollport min-h-24 resize-y rounded-none border-0 bg-transparent px-0 text-base shadow-none focus-visible:ring-0 md:text-base dark:bg-transparent"
              aria-label="修改用户问题"
            />

            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" size="sm" onClick={onCancelEdit}>
                取消
              </Button>

              <Button
                type="button"
                size="sm"
                disabled={!draft.trim() || draft.trim() === turn.question || loading}
                onClick={onSaveEdit}
              >
                保存并发送
              </Button>
            </div>
          </div>
        ) : (
          /* 普通消息模式 */
          <>
            <div className="w-full min-w-0 space-y-3 py-0.5">
              {turn.selection && (
                <blockquote className="border-l-2 border-border pl-3 text-base leading-7 text-muted-foreground">
                  {turn.selection.text}
                </blockquote>
              )}

              <AssistantMarkdown content={turn.question} variant="user" />
            </div>

            <div className="flex items-center gap-1 opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100 [@media(hover:none)]:opacity-100">
              <ActionTooltip label="复制提问">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-8 text-muted-foreground/60 hover:text-foreground"
                  aria-label="复制用户消息"
                  onClick={() => onCopy(copyContent)}
                >
                  {copySucceeded ? <Check className="size-4" /> : <Copy className="size-4" />}
                </Button>
              </ActionTooltip>

              <ActionTooltip label="编辑提问">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-8 text-muted-foreground/60 hover:text-foreground"
                  disabled={loading}
                  aria-label="编辑用户消息"
                  onClick={onStartEdit}
                >
                  <Pencil className="size-4" />
                </Button>
              </ActionTooltip>

              {copyFailed && (
                <span role="alert" className="text-xs text-destructive">
                  复制失败，请手动选择文字复制
                </span>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
