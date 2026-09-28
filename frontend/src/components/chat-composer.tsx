import { ArrowUp, LoaderCircle, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

import type { SelectedText } from "@/components/poem-reader";

type ChatComposerProps = {
  selected: SelectedText | null;
  question: string;
  loading: boolean;
  onQuestionChange: (value: string) => void;
  onClearQuote: () => void;
  onSend: () => void;
};

export function ChatComposer({
  selected,
  question,
  loading,
  onQuestionChange,
  onClearQuote,
  onSend,
}: ChatComposerProps) {
  return (
    <div className="shrink-0 border-t border-border/60 bg-card/50 p-4">
      {/* 用户当前引用的原文 */}
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

      {/* 输入框和发送按钮 */}
      <div className="rounded-2xl border border-input bg-background/70 p-2 transition-colors focus-within:border-violet-400/60 focus-within:ring-2 focus-within:ring-violet-400/10">
        <Textarea
          placeholder="针对诗句提出你的问题……"
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          onKeyDown={(event) => {
            // Shift + Enter：正常换行
            if (event.key !== "Enter" || event.shiftKey) {
              return;
            }

            // 中文输入法还在选字时，不发送
            if (event.nativeEvent.isComposing || event.keyCode === 229) {
              return;
            }

            event.preventDefault();

            // Enter：发送非空问题
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
  );
}
