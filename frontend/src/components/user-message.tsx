import { Check, Copy, Pencil } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

import type { ChatTurn } from "@/components/chat-types";

type CopyStatus = {
  key: string;
  status: "success" | "error";
} | null;

type UserMessageProps = {
  turn: ChatTurn;
  editing: boolean;
  draft: string;
  loading: boolean;
  copyStatus: CopyStatus;

  onDraftChange: (value: string) => void;
  onStartEdit: () => void;
  onCancelEdit: () => void;
  onSaveEdit: () => void;
  onCopy: (content: string) => void;
};

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
  const copyKey = `${turn.id}:user`;

  const copyContent = turn.selection
    ? `引用原文：${turn.selection.text}

问题：${turn.question}`
    : turn.question;

  const copySucceeded =
    copyStatus?.key === copyKey && copyStatus.status === "success";

  const copyFailed =
    copyStatus?.key === copyKey && copyStatus.status === "error";

  return (
    <div className="flex justify-end">
      <div className="group flex max-w-[90%] flex-col items-end gap-1">
        {editing ? (
          /* 编辑模式 */
          <div className="w-full min-w-64 space-y-3 rounded-2xl border border-violet-400/40 bg-secondary p-3">
            {turn.selection && (
              <div className="rounded-lg border-l-2 border-violet-400 bg-background/60 px-3 py-2 text-sm leading-6 text-muted-foreground">
                {turn.selection.text}
              </div>
            )}

            <Textarea
              autoFocus
              value={draft}
              onChange={(event) => onDraftChange(event.target.value)}
              className="min-h-24 resize-y bg-background"
              aria-label="修改用户问题"
            />

            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={onCancelEdit}
              >
                取消
              </Button>

              <Button
                type="button"
                size="sm"
                disabled={
                  !draft.trim() || draft.trim() === turn.question || loading
                }
                onClick={onSaveEdit}
              >
                保存并发送
              </Button>
            </div>
          </div>
        ) : (
          /* 普通消息模式 */
          <>
            <div className="w-full space-y-3 rounded-2xl rounded-tr-md bg-secondary px-4 py-3">
              {turn.selection && (
                <div className="rounded-lg border-l-2 border-violet-400 bg-background/60 px-3 py-2 text-sm leading-6 text-muted-foreground">
                  {turn.selection.text}
                </div>
              )}

              <p className="whitespace-pre-wrap wrap-break-word text-sm leading-7">
                {turn.question}
              </p>
            </div>

            <div className="flex items-center gap-1 opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100 [@media(hover:none)]:opacity-100">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-8 text-muted-foreground/60 hover:text-foreground"
                aria-label="复制用户消息"
                title="复制用户消息"
                onClick={() => onCopy(copyContent)}
              >
                {copySucceeded ? (
                  <Check className="size-4" />
                ) : (
                  <Copy className="size-4" />
                )}
              </Button>

              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-8 text-muted-foreground/60 hover:text-foreground"
                disabled={loading}
                aria-label="编辑用户消息"
                title="编辑"
                onClick={onStartEdit}
              >
                <Pencil className="size-4" />
              </Button>

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
  );
}
