import { useRef, useState } from "react";
import { BookOpenText } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ThemeSwitcher } from "@/components/theme-switcher";
import { PoemReader } from "@/components/poem-reader";
import { ChatPanel } from "@/components/chat-panel";
import { AnalysisPanel } from "@/components/analysis-panel";

import { poem } from "@/data/sample-poem";

import type { SelectedText } from "@/components/poem-reader";
import type { ChatTurn, ChatViewport } from "@/components/chat-types";
import type { PoemAnalysis } from "@/components/analysis-panel";

type ActiveView = "chat" | "analysis";

function App() {
  const [selected, setSelected] = useState<SelectedText | null>(null);
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const inFlightRef = useRef(false);
  const nextTurnId = useRef(0);
  const seenAnimationsRef = useRef(new Set<string>());
  const chatViewportRef = useRef<ChatViewport>({
    scrollTop: 0,
    atBottom: true,
  });
  const [hasUnreadReply, setHasUnreadReply] = useState(false);
  const [activeView, setActiveView] = useState<ActiveView>("chat");
  const [analysis, setAnalysis] = useState<PoemAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState("");

  async function requestReply(turn: ChatTurn, regenerate = false) {
    if (inFlightRef.current) return;

    inFlightRef.current = true;
    setChatLoading(true);

    // 根据是不是重新生成，采用不同的等待状态。
    setTurns((previous) =>
      previous.map((item) => {
        if (item.id !== turn.id) return item;

        if (regenerate) {
          // 保留原来的回答和 done 状态。
          return {
            ...item,
            regenerating: true,
            regenerateError: null,
          };
        }

        // 普通发送或失败重试。
        return {
          ...item,
          status: "pending",
          error: null,
          regenerating: false,
          regenerateError: null,
        };
      }),
    );

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          poem,
          question: turn.question,
          selection: turn.selection,
        }),
      });

      if (!response.ok) {
        const error = await response.json().catch(() => null);

        throw new Error(
          typeof error?.detail === "string"
            ? error.detail
            : `请求失败：HTTP ${response.status}`,
        );
      }

      const result: { answer: string } = await response.json();

      if (typeof result.answer !== "string" || !result.answer.trim()) {
        throw new Error("AI 返回了空回答");
      }

      // 阅读旧消息时不强制滚动，而是在聊天面板显示新回复提醒。
      if (!chatViewportRef.current.atBottom) {
        setHasUnreadReply(true);
      }

      // 成功：把新回答放回原来的消息。
      setTurns((previous) =>
        previous.map((item) =>
          item.id === turn.id
            ? {
                ...item,
                answer: result.answer,
                status: "done",
                error: null,
                regenerating: false,
                regenerateError: null,
              }
            : item,
        ),
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "消息发送失败";

      setTurns((previous) =>
        previous.map((item) => {
          if (item.id !== turn.id) return item;

          if (regenerate) {
            // 重新生成失败：保留原来的回答。
            return {
              ...item,
              regenerating: false,
              regenerateError: message,
            };
          }

          // 普通请求失败：维持原有的重试行为。
          return {
            ...item,
            status: "failed",
            error: message,
            regenerating: false,
          };
        }),
      );
    } finally {
      inFlightRef.current = false;
      setChatLoading(false);
    }
  }

  function handleSend() {
    if (!question.trim() || inFlightRef.current) return;

    const turn: ChatTurn = {
      id: ++nextTurnId.current,
      question: question.trim(),
      selection: selected,
      answer: null,
      status: "pending",
      error: null,

      regenerating: false,
      regenerateError: null,
    };

    // 关键修改：先更新页面，再等待 API。
    setTurns((previous) => [...previous, turn]);
    setQuestion("");
    setSelected(null);

    void requestReply(turn);
  }

  function handleRetry(id: number) {
    if (inFlightRef.current) return;

    const turn = turns.find((item) => item.id === id);

    if (!turn || turn.status !== "failed") return;

    void requestReply(turn);
  }

  function handleRegenerate(id: number) {
    if (inFlightRef.current) return;

    const turn = turns.find((item) => item.id === id);

    if (!turn || turn.status !== "done" || !turn.answer || turn.regenerating) {
      return;
    }

    void requestReply(turn, true);
  }

  function handleEdit(id: number, nextQuestion: string) {
    if (inFlightRef.current || !nextQuestion.trim()) return;

    // 找到用户正在编辑的那一轮。
    const index = turns.findIndex((item) => item.id === id);

    if (index === -1) return;

    const turn = turns[index];

    // 编辑后的新回答应重新播放一次入场动画。
    seenAnimationsRef.current.delete(`assistant:${id}:done`);

    // 保留原来的引用，更新问题。
    const editedTurn: ChatTurn = {
      ...turn,
      question: nextQuestion.trim(),
      answer: null,
      status: "pending",
      error: null,
      regenerating: false,
      regenerateError: null,
    };

    // 保留编辑位置之前的记录，
    // 移除后续记录，并放入修改后的消息。
    setTurns([...turns.slice(0, index), editedTurn]);

    // 使用新问题请求 AI。
    void requestReply(editedTurn);
  }

  async function handleAnalyze() {
    setActiveView("analysis");
    setAnalyzing(true);
    setAnalysisError("");

    try {
      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ poem }),
      });

      if (!response.ok) {
        const error = await response.json().catch(() => null);

        throw new Error(
          typeof error?.detail === "string"
            ? error.detail
            : `请求失败：HTTP ${response.status}`,
        );
      }

      const result: PoemAnalysis = await response.json();
      setAnalysis(result);
    } catch (error) {
      setAnalysisError(error instanceof Error ? error.message : "赏析请求失败");
    } finally {
      setAnalyzing(false);
    }
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border/50 bg-background/70 backdrop-blur-xl">
        <div className="mx-auto flex min-h-20 max-w-7xl flex-wrap items-center justify-between gap-4 px-5 py-4 md:px-8">
          <div className="flex items-center gap-3">
            <div className="flex size-11 items-center justify-center rounded-2xl bg-foreground text-background shadow-lg shadow-black/10">
              <BookOpenText className="size-6" />
            </div>

            <div>
              <div className="text-xl font-semibold tracking-tight">
                Poeticus
              </div>
              <div className="text-xs tracking-wide text-muted-foreground">
                LITERATURE READING STUDIO
              </div>
            </div>
          </div>

          <ThemeSwitcher />
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl px-5 pb-10 pt-10 md:px-8">
        <div className="mb-8">
          <div className="mb-3 text-xs font-medium uppercase tracking-widest text-violet-600 dark:text-violet-300">
            Your reading space
          </div>

          <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
            让阅读成为一场对话
          </h1>

          <p className="mt-3 text-sm leading-7 text-muted-foreground">
            阅读、思考、提问，在诗歌中发现更多可能。
          </p>

          <Button className="mt-5" onClick={handleAnalyze} disabled={analyzing}>
            {analyzing ? "正在赏析……" : "整首赏析"}
          </Button>
        </div>

        <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
          <PoemReader
            onSelect={(value) => {
              if (!chatLoading) setSelected(value);
            }}
          />

          <div className="min-w-0">
            <div
              className="mb-3 flex items-center gap-2"
              role="group"
              aria-label="右侧视图"
            >
              <Button
                type="button"
                variant={activeView === "chat" ? "default" : "ghost"}
                size="sm"
                aria-pressed={activeView === "chat"}
                onClick={() => setActiveView("chat")}
              >
                对话
              </Button>

              <Button
                type="button"
                variant={activeView === "analysis" ? "default" : "ghost"}
                size="sm"
                aria-pressed={activeView === "analysis"}
                onClick={() => setActiveView("analysis")}
              >
                赏析
              </Button>
            </div>

            {activeView === "chat" ? (
              <ChatPanel
                selected={selected}
                question={question}
                turns={turns}
                loading={chatLoading}
                onQuestionChange={setQuestion}
                onClearQuote={() => setSelected(null)}
                onSend={handleSend}
                onRetry={handleRetry}
                onRegenerate={handleRegenerate}
                onEdit={handleEdit}
                seenAnimationsRef={seenAnimationsRef}
                viewportRef={chatViewportRef}
                hasUnreadReply={hasUnreadReply}
                onClearUnreadReply={() => setHasUnreadReply(false)}
              />
            ) : (
              <AnalysisPanel
                analysis={analysis}
                analyzing={analyzing}
                error={analysisError}
              />
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
