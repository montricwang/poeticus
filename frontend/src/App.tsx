import { useCallback, useEffect, useRef, useState } from "react";
import { PanelLeft } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ThemeSwitcher } from "@/components/theme-switcher";
import { PoemReader } from "@/components/poem-reader";
import { PoemCatalog } from "@/components/poem-catalog";
import { ChatPanel } from "@/components/chat-panel";
import { AnalysisPanel } from "@/components/analysis-panel";
import { MobileDiscussionDock } from "@/components/mobile-discussion-dock";
import { ViewToolbar } from "@/components/view-toolbar";
import type { ActiveView } from "@/components/view-toolbar";

import { fetchPoem } from "@/data/poem-library";
import { usePoemCatalog } from "@/hooks/use-poem-catalog";
import { usePoemDetail } from "@/hooks/use-poem-detail";
import { useConversationPersistence } from "@/hooks/use-conversation-persistence";
import { usePoemAnalysis } from "@/hooks/use-poem-analysis";
import { loadInitialChatState } from "@/lib/chat-initial-state";
import { useChatSession } from "@/hooks/use-chat-session";

import type { SelectedText } from "@/components/poem-reader";

function App() {
  const [initialChatState] = useState(loadInitialChatState);
  const [poemId, setPoemId] = useState<string | null>(initialChatState.poemId);

  const {
    catalog,
    filters,
    searchInput,
    setSearchInput,
    catalogLoading,
    catalogError,
    updateCatalogFilters,
  } = usePoemCatalog(setPoemId);
  const [catalogOpen, setCatalogOpen] = useState(
    () => window.matchMedia("(min-width: 1024px)").matches,
  );
  const [wideDiscussionLayout, setWideDiscussionLayout] = useState(
    () => window.matchMedia("(min-width: 1280px)").matches,
  );
  const [mobileDiscussionOpen, setMobileDiscussionOpen] = useState(false);
  const catalogToggleRef = useRef<HTMLButtonElement>(null);
  const switchControllerRef = useRef<AbortController | null>(null);
  const [switchTarget, setSwitchTarget] = useState<string | null>(null);
  const [switchError, setSwitchError] = useState("");

  const [selected, setSelected] = useState<SelectedText | null>(null);
  const {
    activePoem,
    setActivePoem,
    detailError,
    setDetailError,
    detailLoading,
    retryDetail,
  } = usePoemDetail(poemId, setSelected);
  const {
    conversationId,
    question,
    setQuestion,
    turns,
    chatLoading,
    inFlightRef,
    seenAnimationsRef,
    chatViewportRef,
    hasUnreadReply,
    setHasUnreadReply,
    handleReaderSelect,
    restoreForPoem,
    handleSend,
    handleRetry,
    handleRegenerate,
    handleEdit,
  } = useChatSession({
    initialChatState,
    poemId,
    activePoem,
    selected,
    setSelected,
    switchControllerRef,
  });
  const [activeView, setActiveView] = useState<ActiveView>("chat");
  const {
    analysis,
    analyzing,
    analysisError,
    analysisLimitNotice,
    analyzePoem,
    resetAnalysis,
  } = usePoemAnalysis({ poemId, activePoem, switchControllerRef });

  const { persistCurrentConversation } = useConversationPersistence({
    poemId,
    readyPoemId: activePoem?.id ?? null,
    conversationId,
    turns,
    question,
    selected,
  });

  useEffect(() => {
    return () => switchControllerRef.current?.abort();
  }, []);

  useEffect(() => {
    const query = window.matchMedia("(min-width: 1280px)");

    function handleLayoutChange(event: MediaQueryListEvent) {
      setWideDiscussionLayout(event.matches);
      if (event.matches) setMobileDiscussionOpen(false);
    }

    query.addEventListener("change", handleLayoutChange);
    return () => query.removeEventListener("change", handleLayoutChange);
  }, []);

  const closeCatalog = useCallback(() => {
    setCatalogOpen(false);
    catalogToggleRef.current?.focus();
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
        window.getSelection()?.removeAllRanges();
        setActivePoem(work);
        setPoemId(work.id);
        setDetailError("");
        restoreForPoem(work);
        resetAnalysis();
        setActiveView("chat");
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

  function handleAnalyze() {
    if (!activePoem || activePoem.id !== poemId || switchControllerRef.current) return;
    setActiveView("analysis");
    void analyzePoem();
  }

  function handleMobileDiscussionOpenChange(open: boolean) {
    if (open) setActiveView("chat");
    setMobileDiscussionOpen(open);
  }

  const poemReady = !!activePoem && activePoem.id === poemId;

  function renderDiscussionContent(fillAvailableHeight: boolean) {
    if (!activePoem || activePoem.id !== poemId) {
      return (
        <div className="flex h-165 items-center justify-center rounded-md border border-border/60 bg-card text-sm text-muted-foreground">
          加载作品后，即可开始阅读与 AI 讨论。
        </div>
      );
    }

    const fillClassName = fillAvailableHeight ? "h-auto flex-1" : undefined;

    return (
      <>
        <ViewToolbar
          activeView={activeView}
          onViewChange={setActiveView}
          onAnalyze={handleAnalyze}
          analyzing={analyzing}
          switching={!!switchTarget}
        />

        {activeView === "chat" ? (
          <ChatPanel
            key={activePoem.id}
            className={fillClassName}
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
            className={fillClassName}
            analysis={analysis}
            analyzing={analyzing}
            error={analysisError}
            limitNotice={analysisLimitNotice}
          />
        )}
      </>
    );
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

      <main className="mx-auto w-full max-w-[1600px] px-5 pb-24 pt-7 md:px-8 xl:pb-10">
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
                          onClick={retryDetail}
                        >
                          重试
                        </Button>
                      )}
                    </div>
                  )}
                </div>

                {wideDiscussionLayout && (
                  <div className="min-w-0 border-l border-border/60 pl-7">
                    {renderDiscussionContent(false)}
                  </div>
                )}
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

      {poemReady && !wideDiscussionLayout && mobileDiscussionOpen && (
        <div
          className="h-[clamp(16rem,42dvh,28rem)]"
          aria-hidden="true"
        />
      )}

      {poemReady && !wideDiscussionLayout && (
        <MobileDiscussionDock
          open={mobileDiscussionOpen}
          onOpenChange={handleMobileDiscussionOpenChange}
          hasUnreadReply={hasUnreadReply}
          hasSelection={!!selected}
        >
          {renderDiscussionContent(true)}
        </MobileDiscussionDock>
      )}
    </div>
  );
}

export default App;
