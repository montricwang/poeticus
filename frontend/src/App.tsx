import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, MessageCircle, PanelLeft } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ThemeSwitcher } from "@/components/theme-switcher";
import { PoemReader } from "@/components/poem-reader";
import { PoemCatalog } from "@/components/poem-catalog";
import { ChatPanel } from "@/components/chat-panel";
import { AnalysisPanel } from "@/components/analysis-panel";
import { MobileDiscussionScreen } from "@/components/mobile-discussion-screen";
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
    () => window.matchMedia("(min-width: 1536px)").matches,
  );
  const [wideDiscussionLayout, setWideDiscussionLayout] = useState(
    () => window.matchMedia("(min-width: 1024px)").matches,
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
    const query = window.matchMedia("(min-width: 1024px)");

    function handleLayoutChange(event: MediaQueryListEvent) {
      setWideDiscussionLayout(event.matches);
      if (event.matches) {
        setMobileDiscussionOpen(false);
      }
    }

    query.addEventListener("change", handleLayoutChange);
    return () => query.removeEventListener("change", handleLayoutChange);
  }, []);

  const closeCatalog = useCallback(() => {
    setCatalogOpen(false);
    window.requestAnimationFrame(() => catalogToggleRef.current?.focus());
  }, []);

  function handlePoemChange(nextId: string) {
    if (inFlightRef.current || analyzing || !nextId || nextId === poemId) return;

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
        setMobileDiscussionOpen(false);

        if (window.innerWidth < 1536) {
          closeCatalog();
        }
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
    if (!activePoem || activePoem.id !== poemId || switchControllerRef.current) {
      return;
    }

    setActiveView("analysis");
    void analyzePoem();
  }

  function openMobileDiscussion() {
    setCatalogOpen(false);
    setActiveView("chat");
    setMobileDiscussionOpen(true);
  }

  function closeMobileDiscussion() {
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }
    setMobileDiscussionOpen(false);
  }

  const poemReady = !!activePoem && activePoem.id === poemId;

  function renderDiscussionContent(fillAvailableHeight: boolean) {
    if (!poemReady) {
      return (
        <div className="flex h-165 items-center justify-center rounded-md border border-border/60 bg-card text-sm text-muted-foreground">
          加载作品后，即可开始阅读与 AI 讨论。
        </div>
      );
    }

    return (
      <>
        <ViewToolbar
          activeView={activeView}
          onViewChange={setActiveView}
        />

        {activeView === "chat" ? (
          <ChatPanel
            key={activePoem.id}
            fillAvailableHeight={fillAvailableHeight}
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
            fillAvailableHeight={fillAvailableHeight}
            analysis={analysis}
            analyzing={analyzing}
            error={analysisError}
            limitNotice={analysisLimitNotice}
            onAnalyze={handleAnalyze}
            switching={!!switchTarget}
          />
        )}
      </>
    );
  }

  function renderReaderContent() {
    if (poemReady) {
      return (
        <div className="w-full lg:my-auto lg:pt-2 lg:pb-10">
          <PoemReader
            key={activePoem.id}
            work={activePoem}
            onSelect={handleReaderSelect}
          />
        </div>
      );
    }

    return (
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
    );
  }

  function renderCatalog(open: boolean) {
    return (
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
        open={open}
      />
    );
  }

  const showReaderHeader = wideDiscussionLayout || !mobileDiscussionOpen;

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background text-foreground lg:block lg:h-auto lg:min-h-dvh lg:overflow-visible">
      <header className="shrink-0 border-b border-border/50">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 md:px-8">
          {showReaderHeader ? (
            <>
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
                <span className="text-lg font-semibold tracking-tight">
                  Poeticus
                </span>
              </div>
              <ThemeSwitcher />
            </>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  aria-label="返回阅读"
                  onClick={closeMobileDiscussion}
                >
                  <ArrowLeft className="size-5" aria-hidden="true" />
                </Button>
                <span className="text-base font-semibold tracking-tight">
                  阅读讨论
                </span>
              </div>
              <div className="size-9" aria-hidden="true" />
            </>
          )}
        </div>
      </header>

      {!wideDiscussionLayout && (
        <main className="relative min-h-0 flex-1 overflow-hidden">
          <section
            aria-label="诗词阅读"
            aria-hidden={mobileDiscussionOpen}
            inert={mobileDiscussionOpen || catalogOpen}
            className={
              "absolute inset-0 z-10 bg-background " +
              "md:transition-transform md:duration-400 md:ease-[cubic-bezier(0.22,1,0.36,1)] " +
              "motion-reduce:transition-none " +
              (mobileDiscussionOpen ? "md:-translate-x-full" : "md:translate-x-0")
            }
          >
            <div className="h-full overflow-y-auto overscroll-contain px-5 pb-24 pt-7 md:px-8">
              {switchError && (
                <div role="alert" className="mb-3 text-sm text-destructive">
                  作品切换失败：{switchError}。原作品仍可阅读，请重新选择。
                </div>
              )}

              <div className="relative min-w-0" aria-busy={!!switchTarget}>
                <div inert={!!switchTarget}>{renderReaderContent()}</div>

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

            {poemReady && (
              <Button
                type="button"
                size="lg"
                variant="outline"
                className="absolute right-4 bottom-[calc(1rem+env(safe-area-inset-bottom))] z-20 rounded-md bg-background/95 px-4 shadow-sm backdrop-blur-sm"
                aria-controls="mobile-discussion-screen"
                aria-expanded={mobileDiscussionOpen}
                aria-label={selected ? "打开讨论并使用已选诗句提问" : "打开阅读讨论"}
                onClick={openMobileDiscussion}
              >
                <MessageCircle className="size-4" aria-hidden="true" />
                <span>{selected ? "提问" : "对话"}</span>
                {hasUnreadReply && (
                  <span
                    className="size-2 rounded-full bg-violet-300"
                    aria-label="有新回复"
                  />
                )}
              </Button>
            )}
          </section>

          <MobileDiscussionScreen open={mobileDiscussionOpen}>
            {renderDiscussionContent(true)}
          </MobileDiscussionScreen>

          <div
            aria-hidden={!catalogOpen}
            inert={!catalogOpen}
            className={
              "absolute inset-0 z-40 transition-opacity duration-[720ms] " +
              "ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none " +
              "md:transition-none md:opacity-100 " +
              (catalogOpen
                ? "pointer-events-auto opacity-100"
                : "pointer-events-none opacity-0")
            }
          >
            <button
              type="button"
              tabIndex={-1}
              aria-label="关闭作品目录遮罩"
              className={
                "absolute inset-0 bg-black/55 md:transition-opacity md:duration-[520ms] " +
                "md:ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none " +
                (catalogOpen
                  ? "pointer-events-auto md:opacity-100"
                  : "pointer-events-none md:opacity-0")
              }
              onClick={closeCatalog}
            />

            <div
              className={
                "relative h-full w-screen md:w-[min(88vw,420px)] " +
                "md:transform md:transition-transform md:duration-[620ms] " +
                "md:ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none " +
                (catalogOpen
                  ? "pointer-events-auto md:translate-x-0"
                  : "pointer-events-none md:-translate-x-full")
              }
            >
              {renderCatalog(catalogOpen)}
            </div>
          </div>
        </main>
      )}

      {wideDiscussionLayout && (
        <main className="mx-auto w-full max-w-[1600px] px-5 pb-10 pt-7 md:px-8">
          <div
            className={
              "grid min-w-0 grid-cols-1 items-start gap-0 " +
              "2xl:transition-[grid-template-columns] 2xl:duration-[600ms] " +
              "2xl:ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none " +
              (catalogOpen
                ? "2xl:grid-cols-[320px_minmax(0,1fr)]"
                : "2xl:grid-cols-[0px_minmax(0,1fr)]")
            }
          >
            <div
              inert={!catalogOpen}
              aria-hidden={!catalogOpen}
              className={
                "pointer-events-none fixed inset-0 z-50 2xl:sticky 2xl:top-5 2xl:z-auto " +
                "2xl:min-w-0 2xl:overflow-hidden " +
                (catalogOpen
                  ? "2xl:border-r 2xl:border-border/60"
                  : "2xl:border-r-0")
              }
            >
              <button
                type="button"
                tabIndex={-1}
                aria-label="关闭作品目录遮罩"
                className={
                  "absolute inset-0 bg-black/55 transition-opacity duration-[520ms] " +
                  "ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none 2xl:hidden " +
                  (catalogOpen
                    ? "pointer-events-auto opacity-100"
                    : "pointer-events-none opacity-0")
                }
                onClick={closeCatalog}
              />

              <div
                className={
                  "relative h-full w-screen md:w-[min(88vw,420px)] " +
                  "transform transition-transform duration-[620ms] " +
                  "ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none " +
                  "2xl:w-80 2xl:translate-x-0 2xl:pr-5 " +
                  (catalogOpen
                    ? "pointer-events-auto translate-x-0"
                    : "pointer-events-none -translate-x-full")
                }
              >
                {renderCatalog(catalogOpen)}
              </div>
            </div>

            <div className="min-w-0 2xl:pl-6">
              <div className="relative min-w-0" aria-busy={!!switchTarget}>
                {switchError && (
                  <div role="alert" className="mb-3 text-sm text-destructive">
                    作品切换失败：{switchError}。原作品仍可阅读，请重新选择。
                  </div>
                )}

                <div
                  inert={!!switchTarget}
                  className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(340px,0.85fr)]"
                >
                  <div className="min-w-0 lg:flex lg:min-h-[60dvh] lg:max-h-[calc(100dvh-8rem)] lg:flex-col lg:overflow-y-auto lg:overscroll-contain lg:pr-2">
                    {renderReaderContent()}
                  </div>

                  <div className="flex min-h-[60dvh] min-w-0 items-center">
                    <div className="w-full border-l border-border/60 pl-7">
                      {renderDiscussionContent(false)}
                    </div>
                  </div>
                </div>

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
      )}
    </div>
  );
}

export default App;
