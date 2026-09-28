import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { ThemeSwitcher } from "@/components/theme-switcher";
import { PoemReader } from "@/components/poem-reader";
import { ChatPanel } from "@/components/chat-panel";
import { AnalysisPanel } from "@/components/analysis-panel";

import { poem } from "@/data/sample-poem";
import { readChatStream } from "@/lib/chat-stream";

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
    let received = "";

    setTurns((previous) =>
      previous.map((item) => {
        if (item.id !== turn.id) return item;
        if (regenerate) {
          // 原回答继续留在 answer，增量的新回答单独保存在 streamDraft。
          return {
            ...item,
            regenerating: true,
            regenerateError: null,
            streamDraft: "",
          };
        }
        // 普通发送 / 失败重试开始的是一次新的完整生成。
        return {
          ...item,
          answer: null,
          status: "pending",
          error: null,
          regenerating: false,
          regenerateError: null,
          streamDraft: null,
        };
      }),
    );

    try {
      const response = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          poem,
          question: turn.question,
          selection: turn.selection,
        }),
      });

      await readChatStream(response, (token) => {
        received += token;
        setTurns((previous) =>
          previous.map((item) => {
            if (item.id !== turn.id) return item;
            return regenerate
              ? { ...item, streamDraft: received }
              : { ...item, answer: received, status: "streaming" };
          }),
        );
      });

      if (!received.trim()) {
        throw new Error("AI 返回了空回答");
      }

      // 用户阅读旧消息期间不强制跳底部；仅在完成时标记新回复。
      if (!chatViewportRef.current.atBottom) {
        setHasUnreadReply(true);
      }
      setTurns((previous) =>
        previous.map((item) =>
          item.id === turn.id
            ? {
                ...item,
                answer: received,
                streamDraft: null,
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
            // 保留原回答，也保留已经收到的新版本片段。
            return {
              ...item,
              regenerating: false,
              regenerateError: message,
              streamDraft: received || null,
            };
          }
          return {
            ...item,
            answer: received || null,
            status: "failed",
            error: message,
            streamDraft: null,
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
      streamDraft: null,
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
    seenAnimationsRef.current.delete(`assistant:${id}:answer`);

    // 保留原来的引用，更新问题。
    const editedTurn: ChatTurn = {
      ...turn,
      question: nextQuestion.trim(),
      answer: null,
      status: "pending",
      error: null,
      regenerating: false,
      regenerateError: null,
      streamDraft: null,
    };
  
    // 保留编辑位置之前的记录，
    // 移除后续记录，并放入修改后的消息。
    setTurns([
      ...turns.slice(0, index),
      editedTurn,
    ]);
  
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
      <header className="border-b border-border/50">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 md:px-8">
          <span className="text-lg font-semibold tracking-tight">Poeticus</span>
          <ThemeSwitcher />
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl px-5 pb-10 pt-7 md:px-8">
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
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="ml-auto"
                onClick={handleAnalyze}
                disabled={analyzing}
              >
                {analyzing ? "正在生成……" : "生成整首赏析"}
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
