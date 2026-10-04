import { useCallback, useEffect, useRef, useState } from "react";
import { PanelLeft } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ThemeSwitcher } from "@/components/theme-switcher";
import { PoemReader } from "@/components/poem-reader";
import { PoemCatalog } from "@/components/poem-catalog";
import { ChatPanel } from "@/components/chat-panel";
import { AnalysisPanel } from "@/components/analysis-panel";

import {
  fetchPoem,
  fetchPoemPage,
  poemContext,
  poemText,
} from "@/data/poem-library";
import type { Poem, PoemFilters, PoemPage } from "@/data/poem-library";
import { selectionForPython } from "@/lib/selection-offset";
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

const PAGE_SIZE = 20;
const UUID_PATTERN = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;

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
  const lastId = loadLastActivePoemId();
  // 旧 demo 作品使用短字符串 ID；保留旧会话，不将其自动映射到 UUID。
  const poemId = lastId && UUID_PATTERN.test(lastId) ? lastId : null;
  const storedConversation = poemId ? loadPoemConversation(poemId) : null;
  const turns = storedConversation?.turns ?? [];

  return {
    poemId,
    conversationId: storedConversation?.conversationId ?? createConversationId(),
    turns,
    question: storedConversation?.draft.question ?? "",
  };
}

function App() {
  const [initialChatState] = useState(loadInitialChatState);
  const [poemId, setPoemId] = useState<string | null>(initialChatState.poemId);
  const [activePoem, setActivePoem] = useState<Poem | null>(null);
  const poem = activePoem ? poemText(activePoem) : "";

  const [catalog, setCatalog] = useState<PoemPage | null>(null);
  const [filters, setFilters] = useState<PoemFilters>({
    limit: PAGE_SIZE,
    offset: 0,
  });
  const [searchInput, setSearchInput] = useState("");
  const [catalogOpen, setCatalogOpen] = useState(
    () => window.matchMedia("(min-width: 1024px)").matches,
  );
  const catalogToggleRef = useRef<HTMLButtonElement>(null);
  const switchControllerRef = useRef<AbortController | null>(null);
  const [switchTarget, setSwitchTarget] = useState<string | null>(null);
  const [switchError, setSwitchError] = useState("");
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState("");
  const [detailError, setDetailError] = useState("");
  const detailLoading = !!poemId && !activePoem && !detailError;
  const [detailAttempt, setDetailAttempt] = useState(0);

  const [conversationId, setConversationId] = useState(
    initialChatState.conversationId,
  );
  const [selected, setSelected] = useState<SelectedText | null>(null);
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
    readyPoemId: activePoem?.id ?? null,
    turns,
    question,
    selected,
  });
  const [hasUnreadReply, setHasUnreadReply] = useState(false);
  const [activeView, setActiveView] = useState<ActiveView>("chat");
  const [analysis, setAnalysis] = useState<PoemAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisError, setAnalysisError] = useState("");

  // 目录轻量分页，不携带完整正文。
  useEffect(() => {
    const controller = new AbortController();
    void fetchPoemPage(filters, controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return;
        setCatalog(page);
        setPoemId((current) => current ?? page.items[0]?.id ?? null);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setCatalogError(error instanceof Error ? error.message : "无法获取目录");
      })
      .finally(() => {
        if (!controller.signal.aborted) setCatalogLoading(false);
      });
    return () => controller.abort();
  }, [filters]);

  // 首屏／刷新时恢复 UUID；点击切诗由 handlePoemChange 先预取再提交。
  useEffect(() => {
    if (!poemId || activePoem?.id === poemId) return;
    const controller = new AbortController();

    void fetchPoem(poemId, controller.signal)
      .then((work) => {
        if (controller.signal.aborted) return;
        setActivePoem(work);
        setSelected(
          validSelectionForPoem(
            loadPoemConversation(work.id)?.draft.selection ?? null,
            poemText(work),
          ),
        );
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setDetailError(error instanceof Error ? error.message : "无法加载作品");
      })
    return () => controller.abort();
  }, [poemId, activePoem?.id, detailAttempt]);

  useEffect(() => {
    return () => switchControllerRef.current?.abort();
  }, []);

  useEffect(() => {
    persistenceRef.current = {
      conversationId,
      poemId,
      readyPoemId: activePoem?.id ?? null,
      turns,
      question,
      selected,
    };
  }, [activePoem, conversationId, poemId, question, selected, turns]);

  // 本地存储只是 v0.1 的 persistence adapter。
  // 轻微延迟可避免流式 token 到达时同步写 localStorage 过于频繁。
  useEffect(() => {
    if (!poemId || activePoem?.id !== poemId) return;
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
  }, [activePoem, conversationId, poemId, question, selected, turns]);

  // 刷新/关闭页面时，把尚未等到定时写入的最新状态再保存一次。
  useEffect(() => {
    function handlePageHide() {
      const current = persistenceRef.current;
      if (!current.poemId || current.readyPoemId !== current.poemId) return;
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
    if (!poemId || activePoem?.id !== poemId) return;
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

  function updateCatalogFilters(next: PoemFilters) {
    // 上一页目录在请求期间继续存在，避免空列表导致侧栏重排。
    setCatalogLoading(true);
    setCatalogError("");
    setFilters(next);
  }

  const closeCatalog = useCallback(() => {
    setCatalogOpen(false);
    catalogToggleRef.current?.focus();
  }, []);

  // 搜索/翻页也会触发 App 重新渲染；稳定此回调，避免阅读器重复订阅选区事件。
  const handleReaderSelect = useCallback((value: SelectedText) => {
    if (!inFlightRef.current && !switchControllerRef.current) {
      setSelected(value);
    }
  }, []);

  function handlePoemChange(nextId: string) {
    if (inFlightRef.current || analyzing || !nextId || nextId === poemId) return;

    // 先读取新作品；在请求完成前仍显示当前作品，不卸载正文／聊天面板。
    // 最新请求替代旧请求，只有成功的请求才能提交 UUID 与会话状态。
    switchControllerRef.current?.abort();
    const controller = new AbortController();
    switchControllerRef.current = controller;
    setSwitchTarget(nextId);
    setSwitchError("");

    void fetchPoem(nextId, controller.signal)
      .then((work) => {
        if (controller.signal.aborted) return;
        persistCurrentConversation();
        const storedConversation = loadPoemConversation(work.id);
        const nextTurns = storedConversation?.turns ?? [];

        window.getSelection()?.removeAllRanges();
        setActivePoem(work);
        setPoemId(work.id);
        setDetailError("");
        setConversationId(
          storedConversation?.conversationId ?? createConversationId(),
        );
        setSelected(
          validSelectionForPoem(
            storedConversation?.draft.selection ?? null,
            poemText(work),
          ),
        );
        setQuestion(storedConversation?.draft.question ?? "");
        setTurns(nextTurns);
        nextTurnId.current = maxTurnId(nextTurns);

        setAnalysis(null);
        setAnalysisError("");
        setHasUnreadReply(false);
        setActiveView("chat");
        seenAnimationsRef.current.clear();
        chatViewportRef.current = { scrollTop: 0, atBottom: true };
        if (window.innerWidth < 1024) closeCatalog();
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setSwitchError(
          error instanceof Error ? error.message : "切换作品失败，请重试",
        );
      })
      .finally(() => {
        if (controller.signal.aborted) return;
        switchControllerRef.current = null;
        setSwitchTarget(null);
      });
  }

  async function requestReply(turn: ChatTurn, regenerate = false) {
    if (inFlightRef.current || switchControllerRef.current || !activePoem || activePoem.id !== poemId) return;

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
          selection: selectionForPython(turn.selection, poem),
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
    if (!question.trim() || inFlightRef.current || switchControllerRef.current || !activePoem) return;

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
    if (!activePoem || activePoem.id !== poemId || switchControllerRef.current) return;
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
          <div className="flex items-center gap-2">
            <Button
              ref={catalogToggleRef}
              type="button"
              size="icon"
              variant="ghost"
              aria-label={catalogOpen ? "收起作品目录" : "展开作品目录"}
              aria-controls="poem-catalog"
              aria-expanded={catalogOpen}
              onClick={() => setCatalogOpen((current) => !current)}
            >
              <PanelLeft className="size-5" aria-hidden="true" />
            </Button>
            <span className="text-lg font-semibold tracking-tight">Poeticus</span>
          </div>
          <ThemeSwitcher />
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1600px] px-5 pb-10 pt-7 md:px-8">
        <div
          className={
            "grid min-w-0 grid-cols-1 items-start gap-0 " +
            "lg:transition-[grid-template-columns] lg:duration-[360ms] lg:ease-[cubic-bezier(0.4,0,0.2,1)] motion-reduce:transition-none " +
            (catalogOpen
              ? "lg:grid-cols-[320px_minmax(0,1fr)]"
              : "lg:grid-cols-[0px_minmax(0,1fr)]")
          }
        >
          {/* 侧栏保持挂载；只改变 grid 宽度，避免每次开关都重建搜索状态。 */}
          <div
            inert={!catalogOpen}
            aria-hidden={!catalogOpen}
            className={
              "pointer-events-none fixed inset-0 z-50 lg:sticky lg:top-5 lg:z-auto " +
              // 桌面只用 Grid 列宽控制侧栏可见区域，避免 opacity 先于宽度把目录隐去。
              "lg:min-w-0 lg:overflow-hidden " +
              (catalogOpen ? "lg:border-r lg:border-border/60" : "lg:border-r-0")
            }
          >
            <button
              type="button"
              tabIndex={-1}
              aria-label="关闭作品目录遮罩"
              className={
                "absolute inset-0 bg-black/55 transition-opacity duration-[360ms] ease-[cubic-bezier(0.4,0,0.2,1)] " +
                "motion-reduce:transition-none lg:hidden " +
                (catalogOpen ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0")
              }
              onClick={closeCatalog}
            />
            <div
              className={
                "relative h-full w-[min(88vw,360px)] " +
                "transform transition-transform duration-[360ms] ease-[cubic-bezier(0.4,0,0.2,1)] " +
                "motion-reduce:transition-none lg:w-80 lg:translate-x-0 lg:pr-5 " +
                (catalogOpen
                  ? "pointer-events-auto translate-x-0"
                  : "pointer-events-none -translate-x-full")
              }
            >
              <PoemCatalog
                catalog={catalog}
                filters={filters}
                query={searchInput}
                loading={catalogLoading}
                error={catalogError}
                activePoemId={poemId}
                selectionBlocked={chatLoading || analyzing || !!switchTarget}
                onQueryChange={setSearchInput}
                onFiltersChange={updateCatalogFilters}
                onSelect={handlePoemChange}
                onClose={closeCatalog}
                open={catalogOpen}
              />
            </div>
          </div>

          <div className="min-w-0 lg:pl-6">
            <div className="relative min-w-0" aria-busy={!!switchTarget}>
              {switchError && (
                <div role="alert" className="mb-3 text-sm text-destructive">
                  作品切换失败：{switchError}。原作品仍可阅读，请重新选择。
                </div>
              )}
              <div
                inert={!!switchTarget}
                className="grid grid-cols-1 items-start gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]"
              >
                <div className="min-w-0">
                  {activePoem && activePoem.id === poemId ? (
                    <PoemReader
                      key={activePoem.id}
                      work={activePoem}
                      onSelect={handleReaderSelect}
                    />
                  ) : (
                    <div
                      role={detailError ? "alert" : "status"}
                      className="min-h-155 rounded-md border border-border/60 bg-card px-8 py-12 text-sm text-muted-foreground"
                    >
                      {detailLoading
                        ? "正在加载作品正文……"
                        : detailError
                          ? `作品加载失败：${detailError}`
                          : "请从目录中选择作品"}
                      {detailError && (
                        <Button
                          className="ml-3"
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setDetailError("");
                            setActivePoem(null);
                            setSelected(null);
                            setDetailAttempt((count) => count + 1);
                          }}
                        >
                          重试
                        </Button>
                      )}
                    </div>
                  )}
                </div>

                <div className="min-w-0 border-t border-border/60 pt-6 xl:border-l xl:border-t-0 xl:pl-7 xl:pt-0">
                  {activePoem && activePoem.id === poemId ? (
                    <>
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
                          disabled={analyzing || !!switchTarget}
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
                          loading={chatLoading || !!switchTarget}
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
                    </>
                  ) : (
                    <div className="flex h-165 items-center justify-center rounded-md border border-border/60 bg-card text-sm text-muted-foreground">
                      加载作品后，即可开始阅读与 AI 讨论。
                    </div>
                  )}
                </div>
              </div>

              {/* 轻量状态标识，不遮盖／闪白旧页面；原内容暂不允许交互。 */}
              {switchTarget && (
                <div
                  role="status"
                  className="pointer-events-none absolute right-3 top-12 z-10 rounded-md border border-border/60 bg-card px-3 py-1.5 text-xs text-muted-foreground shadow-sm"
                >
                  正在载入下一首……
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
