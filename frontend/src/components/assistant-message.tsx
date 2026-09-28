import { Check, Copy, LoaderCircle, RotateCcw, Sparkles } from "lucide-react";

import { AssistantMarkdown } from "@/components/assistant-markdown";
import { Button } from "@/components/ui/button";

import type { ChatTurn } from "@/components/chat-types";

type CopyStatus = {
  key: string;
  status: "success" | "error";
} | null;

type AssistantMessageProps = {
  turn: ChatTurn;
  loading: boolean;
  copyStatus: CopyStatus;
  onCopy: (content: string) => void;
  onRetry: () => void;
  onRegenerate: () => void;
};

export function AssistantMessage({
  turn,
  loading,
  copyStatus,
  onCopy,
  onRetry,
  onRegenerate,
}: AssistantMessageProps) {
  const copyKey = `${turn.id}:assistant`;

  const copySucceeded =
    copyStatus?.key === copyKey && copyStatus.status === "success";

  const copyFailed =
    copyStatus?.key === copyKey && copyStatus.status === "error";

  // ① AI 正在生成第一版回答
  if (turn.status === "pending") {
    return (
      <div
        role="status"
        className="flex items-center gap-3 text-sm text-muted-foreground"
      >
        <LoaderCircle className="size-4 animate-spin text-violet-500" />
        AI 正在思考……
      </div>
    );
  }

  // ② 首次请求失败
  if (turn.status === "failed") {
    return (
      <div className="rounded-xl border border-destructive/20 bg-destructive/5 p-3">
        <p role="alert" className="mb-3 text-sm leading-6 text-destructive">
          {turn.error ?? "消息发送失败"}
        </p>

        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={loading}
          onClick={onRetry}
        >
          <RotateCcw className="mr-2 size-4" />
          重试
        </Button>
      </div>
    );
  }

  // 没有可显示的回答时，不渲染内容。
  if (!turn.answer) return null;

  // ③ 正常回答，包括重新生成中的状态
  return (
    <div className="flex items-start gap-3">
      {/* AI 头像 */}
      <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-violet-500/10 text-violet-600 dark:text-violet-300">
        <Sparkles className="size-4" />
      </div>

      <div className="group min-w-0 flex-1 select-text pt-1">
        <AssistantMarkdown content={turn.answer} />

        {/* 鼠标移入后显示的操作栏 */}
        <div className="mt-2 flex items-center gap-2 opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100 [@media(hover:none)]:opacity-100">
          {/* 复制回答 */}
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="size-8 text-muted-foreground/60 hover:text-foreground"
            onClick={() => onCopy(turn.answer ?? "")}
            aria-label="复制 AI 回答"
            title="复制 AI 回答"
          >
            {copySucceeded ? (
              <Check className="size-4" />
            ) : (
              <Copy className="size-4" />
            )}
          </Button>

          {/* 重新生成 */}
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

        {/* 重新生成时继续显示原回答 */}
        {turn.regenerating && (
          <div
            role="status"
            className="mt-2 flex items-center gap-2 text-xs text-muted-foreground"
          >
            <LoaderCircle className="size-3 animate-spin" />
            正在重新生成……
          </div>
        )}

        {/* 重新生成失败时保留原回答 */}
        {turn.regenerateError && (
          <div role="alert" className="mt-2 text-xs text-destructive">
            重新生成失败：{turn.regenerateError}
            <span> 可再次点击重新生成。</span>
          </div>
        )}
      </div>
    </div>
  );
}
