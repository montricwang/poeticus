import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type RefObject,
} from "react";
import { ArrowDown, Sparkles } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { MessageEntrance } from "@/components/message-entrance";
import { UserMessage } from "@/components/user-message";
import { AssistantMessage } from "@/components/assistant-message";
import { ChatComposer } from "@/components/chat-composer";
import type { SelectedText } from "@/components/poem-reader";
import type { ChatTurn, ChatViewport } from "@/components/chat-types";

type ChatPanelProps = {
  selected: SelectedText | null;
  question: string;
  turns: ChatTurn[];
  loading: boolean;
  seenAnimationsRef: RefObject<Set<string>>;
  viewportRef: RefObject<ChatViewport>;
  hasUnreadReply: boolean;
  onClearUnreadReply: () => void;
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
  seenAnimationsRef,
  viewportRef,
  hasUnreadReply,
  onClearUnreadReply,
  onQuestionChange,
  onClearQuote,
  onSend,
  onRetry,
  onRegenerate,
  onEdit,
}: ChatPanelProps) {
  const chatListRef = useRef<HTMLDivElement>(null);
  const initializedRef = useRef(false);
  const [isAtBottom, setIsAtBottom] = useState(true);

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

    const timer = window.setTimeout(() => setCopyStatus(null), 2000);
    return () => window.clearTimeout(timer);
  }, [copyStatus]);

  // 首次挂载恢复阅读位置；后续只有在底部时才跟随新消息。
  useLayoutEffect(() => {
    const list = chatListRef.current;
    if (!list) return;

    if (!initializedRef.current) {
      initializedRef.current = true;
      list.scrollTop = viewportRef.current.atBottom
        ? list.scrollHeight
        : viewportRef.current.scrollTop;
    } else if (viewportRef.current.atBottom) {
      list.scrollTop = list.scrollHeight;
    }

    // 在渲染完成后同步按钮状态，避免在 React 渲染期间读取 Ref。
    const frame = window.requestAnimationFrame(() => {
      const atBottom =
        list.scrollHeight - list.scrollTop - list.clientHeight <= 64;
      viewportRef.current.scrollTop = list.scrollTop;
      viewportRef.current.atBottom = atBottom;
      setIsAtBottom(atBottom);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [turns, viewportRef]);

  function handleScroll(list: HTMLDivElement) {
    const distanceToBottom =
      list.scrollHeight - list.scrollTop - list.clientHeight;
    const atBottom = distanceToBottom <= 64;

    viewportRef.current.scrollTop = list.scrollTop;
    viewportRef.current.atBottom = atBottom;
    setIsAtBottom(atBottom);

    if (atBottom && hasUnreadReply) {
      onClearUnreadReply();
    }
  }

  function scrollToBottom() {
    const list = chatListRef.current;
    if (!list) return;

    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    list.scrollTo({
      top: list.scrollHeight,
      behavior: reduceMotion ? "auto" : "smooth",
    });
    // 等 onScroll 确认真正到达底部后，才清除「新回复」提示。
  }

  function handleSendFromComposer() {
    if (!question.trim() || loading) return;

    // 主动发送意味着开始看最新一轮，不再停留在历史消息处。
    viewportRef.current.atBottom = true;
    setIsAtBottom(true);
    onClearUnreadReply();

    const list = chatListRef.current;
    if (list) {
      list.scrollTop = list.scrollHeight;
      viewportRef.current.scrollTop = list.scrollTop;
    }

    onSend();
  }

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

      {/* 相对定位容器负责固定悬浮按钮，内部列表才允许滚动。 */}
      <div className="relative flex min-h-0 flex-1">
        <div
          ref={chatListRef}
          onScroll={(event) => handleScroll(event.currentTarget)}
          className="flex min-h-0 w-full flex-1 flex-col gap-5 overflow-y-auto px-5 py-6"
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
              <MessageEntrance
                animationId={`user:${turn.id}`}
                seenAnimationsRef={seenAnimationsRef}
              >
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
                    const isOlderMessage =
                      turn.id !== turns[turns.length - 1]?.id;

                    if (
                      isOlderMessage &&
                      !window.confirm(
                        "保存后将移除这条消息之后的对话，是否继续？",
                      )
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
              </MessageEntrance>

              <MessageEntrance
                key={`assistant:${turn.id}:${turn.status}`}
                animationId={`assistant:${turn.id}:${turn.status}`}
                seenAnimationsRef={seenAnimationsRef}
                enabled={turn.status === "pending" || turn.status === "done"}
              >
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
              </MessageEntrance>
            </div>
          ))}
        </div>

        {!isAtBottom && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="absolute bottom-4 left-1/2 z-10 -translate-x-1/2 rounded-full bg-background/95 shadow-md backdrop-blur-sm"
            aria-label={
              hasUnreadReply ? "新回复已生成，滚动到底部" : "滚动到底部"
            }
            onClick={scrollToBottom}
          >
            <ArrowDown className="size-4" />
            {hasUnreadReply && (
              <>
                <span className="size-1.5 rounded-full bg-violet-500" />
                <span>新回复</span>
              </>
            )}
          </Button>
        )}
      </div>

      <ChatComposer
        selected={selected}
        question={question}
        loading={loading}
        onQuestionChange={onQuestionChange}
        onClearQuote={onClearQuote}
        onSend={handleSendFromComposer}
      />
    </Card>
  );
}
