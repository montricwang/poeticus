import { useEffect, useRef, useState } from "react";
import {
  ArrowUp,
  Check,
  Copy,
  LoaderCircle,
  RotateCcw,
  Sparkles,
  X,
} from "lucide-react";
import { AssistantMarkdown } from "@/components/assistant-markdown";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";

import type { SelectedText } from "@/components/poem-reader";

export type ChatTurn = {
  id: number;
  question: string;
  selection: SelectedText | null;
  answer: string | null;
  status: "pending" | "done" | "failed";
  error: string | null;
  regenerating: boolean;
  regenerateError: string | null;
};

type ChatPanelProps = {
  selected: SelectedText | null;
  question: string;
  turns: ChatTurn[];
  loading: boolean;
  onQuestionChange: (value: string) => void;
  onClearQuote: () => void;
  onSend: () => void;
  onRetry: (id: number) => void;
  onRegenerate: (id: number) => void;
};

export function ChatPanel({
  selected,
  question,
  turns,
  loading,
  onQuestionChange,
  onClearQuote,
  onSend,
  onRetry,
  onRegenerate,
}: ChatPanelProps) {
  const chatListRef = useRef<HTMLDivElement>(null);

  const [copyStatus, setCopyStatus] = useState<{
    key: string;
    status: "success" | "error";
  } | null>(null);

  async function handleCopy(key: string, content: string) {
    try {
      await navigator.clipboard.writeText(content);
      setCopyStatus({ key, status: "success" });
    } catch {
      setCopyStatus({ key, status: "error" });
    }
  }

  useEffect(() => {
    if (copyStatus?.status !== "success") return;

    const timer = window.setTimeout(() => {
      setCopyStatus(null);
    }, 2000);

    return () => window.clearTimeout(timer);
  }, [copyStatus]);

  useEffect(() => {
    const list = chatListRef.current;

    if (list) {
      list.scrollTop = list.scrollHeight;
    }
  }, [turns]);

  return (
    <Card className="flex h-165 min-h-0 flex-col gap-0 overflow-hidden border-border/60 bg-card/90 py-0 shadow-xl shadow-black/5 backdrop-blur-xl dark:shadow-black/20">
      <header className="flex shrink-0 items-center justify-between border-b border-border/60 px-5 py-5">
        <div className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-2xl bg-violet-500/10 text-violet-600 dark:text-violet-300">
            <Sparkles className="size-5" />
          </div>

          <div>
            <h2 className="text-sm font-semibold">AI 阅读助手</h2>
            <p className="text-xs text-muted-foreground">与诗歌自由对话</p>
          </div>
        </div>

        <span className="rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground">
          AI 对话
        </span>
      </header>

      {/* 聊天记录 */}
      <div
        ref={chatListRef}
        className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-5 py-6"
      >
        {turns.length === 0 && (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
            <div className="flex size-14 items-center justify-center rounded-3xl bg-violet-500/10">
              <Sparkles className="size-7 text-violet-500" />
            </div>

            <div className="max-w-xs space-y-2">
              <h3 className="text-base font-medium">从一句诗开始</h3>
              <p className="text-sm leading-7 text-muted-foreground">
                选中左侧感兴趣的字词或诗句， 然后在这里提出你的问题。
              </p>
            </div>
          </div>
        )}

        {turns.map((turn) => (
          <div key={turn.id} className="space-y-5">
            {/* 用户消息：发送后立即出现 */}
            <div className="flex justify-end">
              <div className="group flex max-w-[90%] flex-col items-end gap-1">
                {/* 原有的用户消息气泡 */}
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

                {/* 新增：用户消息下方的操作栏 */}
                <div className="flex items-center gap-2 opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100 [@media(hover:none)]:opacity-100">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-8 text-muted-foreground/60 hover:text-foreground"
                    aria-label="复制用户消息"
                    title="复制用户消息"
                    onClick={() =>
                      void handleCopy(
                        `${turn.id}:user`,
                        turn.selection
                          ? `引用原文：${turn.selection.text}

问题：${turn.question}`
                          : turn.question,
                      )
                    }
                  >
                    {copyStatus?.key === `${turn.id}:user` &&
                    copyStatus.status === "success" ? (
                      <Check className="size-4" />
                    ) : (
                      <Copy className="size-4" />
                    )}
                  </Button>

                  {/* 只有当前用户消息复制失败时才显示提示 */}
                  {copyStatus?.key === `${turn.id}:user` &&
                    copyStatus.status === "error" && (
                      <span role="alert" className="text-xs text-destructive">
                        复制失败，请手动选择文字复制
                      </span>
                    )}
                </div>
              </div>
            </div>

            {/* AI 正在生成 */}
            {turn.status === "pending" && (
              <div
                role="status"
                className="flex items-center gap-3 text-sm text-muted-foreground"
              >
                <LoaderCircle className="size-4 animate-spin text-violet-500" />
                AI 正在思考……
              </div>
            )}

            {/* 正常回答 */}
            {turn.status === "done" && turn.answer && (
              <div className="flex items-start gap-3">
                {/* AI 头像 */}
                <div className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-violet-500/10 text-violet-600 dark:text-violet-300">
                  <Sparkles className="size-4" />
                </div>

                {/* AI 回答正文与操作区 */}
                <div className="group min-w-0 flex-1 select-text pt-1">
                  {/* 重新生成期间，旧回答仍然显示 */}
                  <AssistantMarkdown content={turn.answer} />

                  {/* 复制与重新生成按钮 */}
                  <div className="mt-2 flex items-center gap-2 opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100 [@media(hover:none)]:opacity-100">
                    {/* 复制按钮 */}
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="size-8 text-muted-foreground/60 hover:text-foreground"
                      onClick={() =>
                        void handleCopy(
                          `${turn.id}:assistant`,
                          turn.answer ?? "",
                        )
                      }
                      aria-label="复制 AI 回答"
                      title="复制 AI 回答"
                    >
                      {copyStatus?.key === `${turn.id}:assistant` &&
                      copyStatus.status === "success" ? (
                        <Check className="size-4" />
                      ) : (
                        <Copy className="size-4" />
                      )}
                    </Button>

                    {/* 重新生成按钮 */}
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="size-8 text-muted-foreground/60 hover:text-foreground"
                      onClick={() => onRegenerate(turn.id)}
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

                    {/* 复制失败提示 */}
                    {copyStatus?.key === `${turn.id}:assistant` &&
                      copyStatus.status === "error" && (
                        <span role="alert" className="text-xs text-destructive">
                          复制失败，请手动选择文字复制
                        </span>
                      )}
                  </div>

                  {/* 正在重新生成 */}
                  {turn.regenerating && (
                    <div
                      role="status"
                      className="mt-2 flex items-center gap-2 text-xs text-muted-foreground"
                    >
                      <LoaderCircle className="size-3 animate-spin" />
                      正在重新生成……
                    </div>
                  )}

                  {/* 重新生成失败，但不删除旧回答 */}
                  {turn.regenerateError && (
                    <div role="alert" className="mt-2 text-xs text-destructive">
                      重新生成失败：{turn.regenerateError}
                      <span> 可再次点击重新生成。</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 请求失败：保留原消息，原位重试 */}
            {turn.status === "failed" && (
              <div className="rounded-xl border border-destructive/20 bg-destructive/5 p-3">
                <p
                  role="alert"
                  className="mb-3 text-sm leading-6 text-destructive"
                >
                  {turn.error ?? "消息发送失败"}
                </p>

                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={loading}
                  onClick={() => onRetry(turn.id)}
                >
                  <RotateCcw className="mr-2 size-4" />
                  重试
                </Button>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* 底部：引用与输入框 */}
      <div className="shrink-0 border-t border-border/60 bg-card/50 p-4">
        {selected && (
          <div className="mb-3 rounded-xl border border-violet-400/20 bg-violet-500/5 p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-medium text-violet-600 dark:text-violet-300">
                引用原文
              </span>

              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-7 rounded-full"
                onClick={onClearQuote}
                disabled={loading}
                aria-label="移除引用"
              >
                <X className="size-4" />
              </Button>
            </div>

            <p className="font-serif text-sm leading-7 text-foreground/85">
              {selected.text}
            </p>
          </div>
        )}

        <div className="rounded-2xl border border-input bg-background/70 p-2 transition-colors focus-within:border-violet-400/60 focus-within:ring-2 focus-within:ring-violet-400/10">
          <Textarea
            placeholder="针对诗句提出你的问题……"
            value={question}
            onChange={(event) => onQuestionChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key !== "Enter" || event.shiftKey) {
                return;
              }

              if (event.nativeEvent.isComposing || event.keyCode === 229) {
                return;
              }

              event.preventDefault();

              if (!loading && question.trim()) {
                onSend();
              }
            }}
            disabled={loading}
            className="min-h-24 resize-none border-0 bg-transparent shadow-none focus-visible:ring-0 dark:bg-transparent"
          />

          <div className="flex items-center justify-between px-2 pb-1">
            <span className="text-xs text-muted-foreground">
              {loading ? "正在等待 AI 回复" : "Enter 发送 · Shift+Enter 换行"}
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
    </Card>
  );
}
