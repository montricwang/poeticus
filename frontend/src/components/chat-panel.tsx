import { useEffect, useRef, useState } from "react";
import { Sparkles } from "lucide-react";
import { Card } from "@/components/ui/card";
import { UserMessage } from "@/components/user-message";
import { AssistantMessage } from "@/components/assistant-message";
import { ChatComposer } from "@/components/chat-composer";
import type { SelectedText } from "@/components/poem-reader";
import type { ChatTurn } from "@/components/chat-types";

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
  onEdit: (id: number, nextQuestion: string) => void;
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
  onEdit,
}: ChatPanelProps) {
  const chatListRef = useRef<HTMLDivElement>(null);

  const [copyStatus, setCopyStatus] = useState<{
    key: string;
    status: "success" | "error";
  } | null>(null);

  const [editingTurnId, setEditingTurnId] = useState<number | null>(null);

  const [editDraft, setEditDraft] = useState("");

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
            {/* 用户消息 */}
            <UserMessage
              turn={turn}
              editing={editingTurnId === turn.id}
              draft={editDraft}
              loading={loading}
              copyStatus={copyStatus}
              onDraftChange={setEditDraft}
              onStartEdit={() => {
                setEditingTurnId(turn.id);
                setEditDraft(turn.question);
              }}
              onCancelEdit={() => {
                setEditingTurnId(null);
                setEditDraft("");
              }}
              onSaveEdit={() => {
                const isOlderMessage = turn.id !== turns[turns.length - 1]?.id;

                if (
                  isOlderMessage &&
                  !window.confirm("保存后将移除这条消息之后的对话，是否继续？")
                ) {
                  return;
                }

                onEdit(turn.id, editDraft.trim());
                setEditingTurnId(null);
                setEditDraft("");
              }}
              onCopy={(content) => {
                void handleCopy(`${turn.id}:user`, content);
              }}
            />

            {/* AI 消息 */}
            <AssistantMessage
              turn={turn}
              loading={loading}
              copyStatus={copyStatus}
              onCopy={(content) => {
                void handleCopy(`${turn.id}:assistant`, content);
              }}
              onRetry={() => onRetry(turn.id)}
              onRegenerate={() => onRegenerate(turn.id)}
            />
          </div>
        ))}
      </div>

      {/* 底部：引用与输入框 */}
      <ChatComposer
        selected={selected}
        question={question}
        loading={loading}
        onQuestionChange={onQuestionChange}
        onClearQuote={onClearQuote}
        onSend={onSend}
      />
    </Card>
  );
}
