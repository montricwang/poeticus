import { ArrowUp, Sparkles, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";

import type { SelectedText } from "@/components/poem-reader";

// 一条已经发送的聊天消息
export type ChatMessage = {
  question: string;
  quote: string | null;
};

// App.tsx 传给聊天组件的数据和操作
type ChatPanelProps = {
  selected: SelectedText | null;
  question: string;
  messages: ChatMessage[];
  onQuestionChange: (value: string) => void;
  onClearQuote: () => void;
  onSend: () => void;
};

export function ChatPanel({
  selected,
  question,
  messages,
  onQuestionChange,
  onClearQuote,
  onSend,
}: ChatPanelProps) {
  return (
    <Card className="flex h-[660px] min-h-0 flex-col gap-0 overflow-hidden border-border/60 bg-card/90 py-0 shadow-xl shadow-black/5 backdrop-blur-xl dark:shadow-black/20">
      {/* 顶部：AI 阅读助手 */}
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
          本地演示
        </span>
      </header>

      {/* 中间：聊天记录 */}
      <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-5 py-6">
        {/* 尚无消息时的欢迎界面 */}
        {messages.length === 0 && (
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

        {/* 已发送的消息 */}
        {messages.map((message, index) => (
          <div key={index} className="flex justify-end">
            <div className="max-w-[90%] space-y-3 rounded-2xl rounded-tr-md bg-secondary px-4 py-3">
              {/* 消息中附带的原文引用 */}
              {message.quote && (
                <div className="rounded-lg border-l-2 border-violet-400 bg-background/60 px-3 py-2 text-sm leading-6 text-muted-foreground">
                  {message.quote}
                </div>
              )}

              <p className="whitespace-pre-wrap text-sm leading-7">
                {message.question}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* 底部：引用卡片和消息输入框 */}
      <div className="shrink-0 border-t border-border/60 bg-card/50 p-4">
        {/* 尚未发送的原文引用 */}
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

        {/* 输入框 */}
        <div className="rounded-2xl border border-input bg-background/70 p-2 transition-colors focus-within:border-violet-400/60 focus-within:ring-2 focus-within:ring-violet-400/10">
          <Textarea
            placeholder="针对诗句提出你的问题……"
            value={question}
            onChange={(event) => onQuestionChange(event.target.value)}
            className="min-h-24 resize-none border-0 bg-transparent shadow-none focus-visible:ring-0 dark:bg-transparent"
          />

          <div className="flex items-center justify-between px-2 pb-1">
            <span className="text-xs text-muted-foreground">
              目前仅演示本地聊天
            </span>

            <Button
              type="button"
              size="icon"
              className="rounded-xl"
              onClick={onSend}
              disabled={!question.trim()}
              aria-label="发送消息"
            >
              <ArrowUp className="size-4" />
            </Button>
          </div>
        </div>
      </div>
    </Card>
  );
}
