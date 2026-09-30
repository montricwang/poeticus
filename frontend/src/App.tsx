import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { ThemeSwitcher } from "@/components/theme-switcher";
import { PoemReader } from "@/components/poem-reader";
import { ChatPanel } from "@/components/chat-panel";
import { AnalysisPanel } from "@/components/analysis-panel";

import { poems, poemContext, poemText } from "@/data/poem-library";
import { readChatStream } from "@/lib/chat-stream";
import {
  createConversationId,
  loadLastActivePoemId,
  loadPoemConversation,
  saveLastActivePoemId,
  savePoemConversation,
} from "@/lib/chat-storage";

import type { SelectedText } from "@/components/poem-reader";
import type {
  ChatTurn,
  ChatViewport,
  HistoryMessage,
} from "@/components/chat-types";
import type { PoemAnalysis } from "@/components/analysis-panel";

type ActiveView = "chat" | "analysis";

const DEFAULT_POEM_ID = "su-shi-huan-xi-sha-feng-juan-zhu-lian";

const MAX_HISTORY_TURNS = 6;

function historyUserContent(turn: ChatTurn) {
  if (!turn.selection) {
    return turn.question;
  }

  return `引用原文：${turn.selection.text}\n\n问题：${turn.question}`;
}

function buildHistory(
  turns: ChatTurn[],
  currentTurnId: number,
): HistoryMessage[] {
  const currentIndex = turns.findIndex((turn) => turn.id === currentTurnId);

  // 新发送的 Turn 还没进入当前 render 的 turns，因此找不到时，
  // 当前已有 turns 全部都是它之前的历史。
  const previousTurns =
    currentIndex === -1 ? turns : turns.slice(0, currentIndex);

  const completedTurns = previousTurns
    .filter(
      (turn) =>
        turn.status === "done" &&
        turn.answer !== null &&
        turn.answer.trim() !== "",
    )
    .slice(-MAX_HISTORY_TURNS);

  return completedTurns.flatMap((turn) => [
    {
      role: "user" as const,
      content: historyUserContent(turn),
    },
    {
      role: "assistant" as const,
      content: turn.answer!.trim(),
    },
  ]);
}

function validSelectionForPoem(
  selection: SelectedText | null,
  poem: string,
): SelectedText | null {
  if (!selection) return null;

  if (
    selection.start < 0 ||
    selection.end > poem.length ||
    selection.start >= selection.end ||
    poem.slice(selection.start, selection.end) !== selection.text
  ) {
    return null;
  }

  return selection;
}

function maxTurnId(turns: ChatTurn[]): number {
  return turns.reduce((max, turn) => Math.max(max, turn.id), 0);
}

function loadInitialChatState() {
  const storedPoemId = loadLastActivePoemId();
  const initialPoem =
    poems.find((item) => item.id === storedPoemId) ??
    poems.find((item) => item.id === DEFAULT_POEM_ID) ??
    poems[0];

  const storedConversation = loadPoemConversation(initialPoem.id);
  const turns = storedConversation?.turns ?? [];

  return {
    poemId: initialPoem.id,
    conversationId:
      storedConversation?.conversationId ?? createConversationId(),
    turns,
    question: storedConversation?.draft.question ?? "",
    selected: validSelectionForPoem(
      storedConversation?.draft.selection ?? null,
      poemText(initialPoem),
    ),
  };
}

function App() {
  const [initialChatState] = useState(loadInitialChatState);
  const [poemId, setPoemId] = useState(initialChatState.poemId);
  const activePoem = poems.find((item) => item.id === poemId) ?? poems[0];
  const poem = poemText(activePoem);

  const [conversationId, setConversationId] = useState(
    initialChatState.conversationId,
  );
  const [selected, setSelected] = useState<SelectedText | null>(
    initialChatState.selected,
  );
  const [question, setQuestion] = useState(initialChatState.question);
  const [turns, setTurns] = useState<ChatTurn[]>(initialChatState.turns);
  const [chatLoading, setChatLoading] = useState(false);
  const inFlightRef = useRef(false);
  const nextTurnId = useRef(maxTurnId(initialChatState.turns));
  const seenAnimationsRef = useRef(new Set<string>());
  const chatViewportRef = useRef<ChatViewport>({
    scrollTop: 0,
    atBottom: true,
  });
  const persistenceRef = useRef({
    conversationId,
    poemId,
    turns,
    question,
    selected,
  });
  const [hasUnreadReply, setHasUnreadReply] = useState(false);
  const [activeView, setActiveView] = useState<ActiveView>("chat");
  const [analysis, setAnalysis] = useState<PoemAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState("");

  useEffect(() => {
    persistenceRef.current = {
      conversationId,
      poemId,
      turns,
      question,
      selected,
    };
  }, [conversationId, poemId, question, selected, turns]);

  // 本地存储只是 v0.1 的 persistence adapter。
  // 轻微延迟可避免流式 token 到达时同步写 localStorage 过于频繁。
  useEffect(() => {
    const timer = window.setTimeout(() => {
      saveLastActivePoemId(poemId);
      savePoemConversation({
        conversationId,
        poemId,
        turns,
        draft: {
          question,
          selection: selected,
        },
      });
    }, 200);

    return () => window.clearTimeout(timer);
  }, [conversationId, poemId, question, selected, turns]);

  // 刷新/关闭页面时，把尚未等到定时写入的最新状态再保存一次。
  useEffect(() => {
    function handlePageHide() {
      const current = persistenceRef.current;
      saveLastActivePoemId(current.poemId);
      savePoemConversation({
        conversationId: current.conversationId,
        poemId: current.poemId,
        turns: current.turns,
        draft: {
          question: current.question,
          selection: current.selected,
        },
      });
    }

    window.addEventListener("pagehide", handlePageHide);
    return () => window.removeEventListener("pagehide", handlePageHide);
  }, []);

  function persistCurrentConversation() {
    saveLastActivePoemId(poemId);
    savePoemConversation({
      conversationId,
      poemId,
      turns,
      draft: {
        question,
        selection: selected,
      },
    });
  }

  function handlePoemChange(nextId: string) {
    if (inFlightRef.current || analyzing || nextId === activePoem.id) return;

    const nextPoem = poems.find((item) => item.id === nextId);
    if (!nextPoem) return;

    // 切换作品前先保存当前会话，再恢复目标作品自己的会话和草稿。
    persistCurrentConversation();

    const storedConversation = loadPoemConversation(nextId);
    const nextTurns = storedConversation?.turns ?? [];
    const nextSelection = validSelectionForPoem(
      storedConversation?.draft.selection ?? null,
      poemText(nextPoem),
    );

    window.getSelection()?.removeAllRanges();
    setPoemId(nextId);
    setConversationId(
      storedConversation?.conversationId ?? createConversationId(),
    );
    setSelected(nextSelection);
    setQuestion(storedConversation?.draft.question ?? "");
    setTurns(nextTurns);
    nextTurnId.current = maxTurnId(nextTurns);

    setAnalysis(null);
    setAnalysisError("");
    setHasUnreadReply(false);
    setActiveView("chat");
    seenAnimationsRef.current.clear();
    chatViewportRef.current = { scrollTop: 0, atBottom: true };
  }

  async function requestReply(turn: ChatTurn, regenerate = false) {
    if (inFlightRef.current) return;

    const history = buildHistory(turns, turn.id);

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
          context: poemContext(activePoem),
          history,
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

    setTurns((previous) => [...previous, turn]);
    setQuestion("");
    setSelected(null);

    void requestReply(turn);
  }

  function handleRetry(id: number) {
    if (inFlightRef.current) return;

    const index = turns.findIndex((item) => item.id === id);
    if (index === -1) return;

    const turn = turns[index];
    if (turn.status !== "failed") return;

    // 重试旧轮次会改变过去，因此丢弃它之后的对话。
    setTurns(turns.slice(0, index + 1));
    void requestReply(turn);
  }

  function handleRegenerate(id: number) {
    if (inFlightRef.current) return;

    const index = turns.findIndex((item) => item.id === id);
    if (index === -1) return;

    const turn = turns[index];
    if (turn.status !== "done" || !turn.answer || turn.regenerating) {
      return;
    }

    // 重新生成旧轮次会改变过去，因此丢弃它之后的对话。
    setTurns(turns.slice(0, index + 1));
    void requestReply(turn, true);
  }

  function handleEdit(id: number, nextQuestion: string) {
    if (inFlightRef.current || !nextQuestion.trim()) return;
    const index = turns.findIndex((item) => item.id === id);
    if (index === -1) return;
    const turn = turns[index];

    seenAnimationsRef.current.delete(`assistant:${id}:answer`);
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

    setTurns([...turns.slice(0, index), editedTurn]);
    void requestReply(editedTurn);
  }

  async function handleAnalyze() {
    setActiveView("analysis");
    setAnalyzing(true);
    setAnalysisError("");

    try {
      const response = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          poem,
          context: poemContext(activePoem),
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
        <div className="mb-6 flex flex-wrap items-center gap-3">
          <label
            htmlFor="poem-picker"
            className="text-sm text-muted-foreground"
          >
            当前作品
          </label>
          <select
            id="poem-picker"
            value={activePoem.id}
            disabled={chatLoading || analyzing}
            onChange={(event) => handlePoemChange(event.target.value)}
            className="max-w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground disabled:opacity-50"
          >
            {poems.map((work) => (
              <option key={work.id} value={work.id}>
                {work.title} · {work.author ?? "作者未核实"}
              </option>
            ))}
          </select>
        </div>

        <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
          <PoemReader
            key={activePoem.id}
            work={activePoem}
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
                key={activePoem.id}
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
