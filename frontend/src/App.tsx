import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { ArrowLeft, MessageCircle, PanelLeft } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { ThemeSwitcher } from '@/components/theme-switcher'
import { PoemReader } from '@/components/poem-reader'
import { ReaderNavigation } from '@/components/reader-navigation'
import { PoemCatalog } from '@/components/poem-catalog'
import { DesktopCompanionStage } from '@/components/desktop-companion-stage'
import { HorizontalEditorialDivider } from '@/components/editorial-divider'
import { ChatPanel } from '@/components/chat-panel'
import { AnalysisPanel } from '@/components/analysis-panel'
import { MobileDiscussionScreen } from '@/components/mobile-discussion-screen'
import { ViewToolbar } from '@/components/view-toolbar'
import type { ActiveView } from '@/components/view-toolbar'

import { fetchPoem } from '@/data/poem-library'
import { usePoemCatalog } from '@/hooks/use-poem-catalog'
import { usePoemDetail } from '@/hooks/use-poem-detail'
import { usePoemNeighbors } from '@/hooks/use-poem-neighbors'
import { useConversationPersistence } from '@/hooks/use-conversation-persistence'
import { usePoemAnalysis } from '@/hooks/use-poem-analysis'
import { loadInitialChatState } from '@/lib/chat-initial-state'
import {
  PERSISTENT_CATALOG_MEDIA,
  PERSISTENT_CATALOG_MIN_WIDTH,
  WIDE_DISCUSSION_MEDIA,
} from '@/lib/responsive-layout'
import { useChatSession } from '@/hooks/use-chat-session'

import type { SelectedText } from '@/types/poem'

function App() {
  const [initialChatState] = useState(loadInitialChatState)
  const [poemId, setPoemId] = useState<string | null>(initialChatState.poemId)

  const {
    catalog,
    filters,
    searchInput,
    setSearchInput,
    catalogLoading,
    catalogError,
    updateCatalogFilters,
  } = usePoemCatalog(setPoemId)

  // 这些宽度是交互模式切换边界，不只是视觉断点：
  // 1024px 起阅读器与伴读区并排；1536px 起目录保持常驻。
  const [catalogOpen, setCatalogOpen] = useState(
    () => window.matchMedia(PERSISTENT_CATALOG_MEDIA).matches,
  )
  const [wideDiscussionLayout, setWideDiscussionLayout] = useState(
    () => window.matchMedia(WIDE_DISCUSSION_MEDIA).matches,
  )
  const [mobileDiscussionOpen, setMobileDiscussionOpen] = useState(false)
  const readerScrollRef = useRef<HTMLDivElement>(null)
  const [readerHasContentAbove, setReaderHasContentAbove] = useState(false)
  const [readerHasContentBelow, setReaderHasContentBelow] = useState(false)

  const catalogToggleRef = useRef<HTMLButtonElement>(null)
  const switchControllerRef = useRef<AbortController | null>(null)
  const [switchTarget, setSwitchTarget] = useState<string | null>(null)
  const [switchError, setSwitchError] = useState('')
  const [poemSwapPhase, setPoemSwapPhase] = useState<'steady' | 'leaving' | 'arriving'>('steady')

  const [selected, setSelected] = useState<SelectedText | null>(null)
  const { activePoem, setActivePoem, detailError, setDetailError, detailLoading, retryDetail } =
    usePoemDetail(poemId, setSelected)

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
  })

  const neighbors = usePoemNeighbors(poemId)

  const [activeView, setActiveView] = useState<ActiveView>('chat')
  // 赏析面板切换视图时会卸载；用 ref 保留已读位置，不触发整页重渲染。
  const analysisScrollTopRef = useRef(0)
  const [viewFadingOut, setViewFadingOut] = useState(false)
  const viewSwitchTimerRef = useRef<number | null>(null)
  const [animatedAnalysisId, setAnimatedAnalysisId] = useState<string | null>(null)
  const { analysis, analyzing, analysisError, analysisLimitNotice, analyzePoem, resetAnalysis } =
    usePoemAnalysis({ poemId, activePoem, switchControllerRef })

  const { persistCurrentConversation } = useConversationPersistence({
    poemId,
    readyPoemId: activePoem?.id ?? null,
    conversationId,
    turns,
    question,
    selected,
  })

  useEffect(() => {
    return () => {
      switchControllerRef.current?.abort()
      if (viewSwitchTimerRef.current !== null) window.clearTimeout(viewSwitchTimerRef.current)
    }
  }, [])

  const updateReaderScrollEdges = useCallback((element: HTMLDivElement) => {
    const remaining = element.scrollHeight - element.clientHeight - element.scrollTop
    setReaderHasContentAbove(element.scrollTop > 8)
    setReaderHasContentBelow(remaining > 8)
  }, [])

  useLayoutEffect(() => {
    const element = readerScrollRef.current
    if (!element) return

    let active = true
    const update = () => {
      if (active) updateReaderScrollEdges(element)
    }
    const observer = new ResizeObserver(update)
    observer.observe(element)
    const content = element.querySelector('.poem-reader')
    if (content) observer.observe(content)
    void document.fonts.ready.then(update)
    return () => {
      active = false
      observer.disconnect()
    }
  }, [activePoem, poemId, wideDiscussionLayout, updateReaderScrollEdges])

  useEffect(() => {
    const query = window.matchMedia(WIDE_DISCUSSION_MEDIA)

    function handleLayoutChange(event: MediaQueryListEvent) {
      setWideDiscussionLayout(event.matches)
      if (event.matches) {
        setMobileDiscussionOpen(false)
      }
    }

    query.addEventListener('change', handleLayoutChange)
    return () => query.removeEventListener('change', handleLayoutChange)
  }, [])

  const closeCatalog = useCallback(() => {
    setCatalogOpen(false)
    window.requestAnimationFrame(() => catalogToggleRef.current?.focus())
  }, [])

  function handleViewChange(nextView: ActiveView) {
    if (nextView === activeView) {
      if (viewSwitchTimerRef.current !== null) {
        window.clearTimeout(viewSwitchTimerRef.current)
        viewSwitchTimerRef.current = null
        setViewFadingOut(false)
      }
      return
    }
    if (viewSwitchTimerRef.current !== null) window.clearTimeout(viewSwitchTimerRef.current)
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setActiveView(nextView)
      setViewFadingOut(false)
      viewSwitchTimerRef.current = null
      return
    }
    setViewFadingOut(true)
    viewSwitchTimerRef.current = window.setTimeout(() => {
      setActiveView(nextView)
      setViewFadingOut(false)
      viewSwitchTimerRef.current = null
    }, 150)
  }

  function handlePoemChange(nextId: string) {
    if (inFlightRef.current || analyzing || !nextId || nextId === poemId) return

    switchControllerRef.current?.abort()
    const controller = new AbortController()
    switchControllerRef.current = controller
    setSwitchTarget(nextId)
    setSwitchError('')

    void fetchPoem(nextId, controller.signal)
      .then(async (work) => {
        if (controller.signal.aborted) return

        // Avoid a blank screen during network waits; fade only after data arrives.
        const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
        if (!reduceMotion) {
          setPoemSwapPhase('leaving')
          await new Promise<void>((resolve) => window.setTimeout(resolve, 300))
          if (controller.signal.aborted) return
        }

        persistCurrentConversation()
        window.getSelection()?.removeAllRanges()
        setActivePoem(work)
        setPoemId(work.id)
        readerScrollRef.current?.scrollTo({ top: 0 })
        setDetailError('')
        restoreForPoem(work)
        setAnimatedAnalysisId(null)
        resetAnalysis()
        analysisScrollTopRef.current = 0
        if (viewSwitchTimerRef.current !== null) window.clearTimeout(viewSwitchTimerRef.current)
        viewSwitchTimerRef.current = null
        setViewFadingOut(false)
        setActiveView('chat')
        setMobileDiscussionOpen(false)

        if (window.innerWidth < PERSISTENT_CATALOG_MIN_WIDTH) {
          closeCatalog()
        }

        if (!reduceMotion) {
          // Commit the restored poem, messages, composer and quote while hidden.
          // Two frames give React and companion layout effects time to measure.
          setPoemSwapPhase('arriving')
          await new Promise<void>((resolve) => {
            window.requestAnimationFrame(() => window.requestAnimationFrame(() => resolve()))
          })
          if (controller.signal.aborted) return
          setPoemSwapPhase('steady')
          await new Promise<void>((resolve) => window.setTimeout(resolve, 360))
        }
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setPoemSwapPhase('steady')
        setSwitchError(error instanceof Error ? error.message : '切换作品失败，请重试')
      })
      .finally(() => {
        if (controller.signal.aborted) return
        switchControllerRef.current = null
        setSwitchTarget(null)
      })
  }

  function handleAnalyze() {
    if (!activePoem || activePoem.id !== poemId || switchControllerRef.current) {
      return
    }

    // 重新生成时从赏析开头阅读，不沿用上一份结果的滚动位置。
    analysisScrollTopRef.current = 0
    setActiveView('analysis')
    void analyzePoem()
  }

  function openMobileDiscussion() {
    setCatalogOpen(false)
    setActiveView('chat')
    setMobileDiscussionOpen(true)
  }

  function closeMobileDiscussion() {
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur()
    }
    setMobileDiscussionOpen(false)
  }

  const poemReady = !!activePoem && activePoem.id === poemId
  // Old poem stays visible during fetch; both columns use the same swap phase.
  const poemTransitionClass =
    'transition-[opacity,transform] duration-[360ms] ease-[var(--motion-ease-settle)] motion-reduce:transition-none ' +
    (poemSwapPhase === 'leaving'
      ? '-translate-y-1 opacity-0'
      : poemSwapPhase === 'arriving'
        ? 'translate-y-1 opacity-0'
        : 'translate-y-0 opacity-100')

  function handleReaderScroll(element: HTMLDivElement) {
    updateReaderScrollEdges(element)
  }

  function renderDiscussionContent(fillAvailableHeight: boolean) {
    if (!poemReady) {
      return (
        <div className="flex h-165 items-center justify-center rounded-md border border-border/60 bg-card text-sm text-muted-foreground">
          加载作品后，即可开始阅读与 AI 讨论。
        </div>
      )
    }

    return (
      <>
        {/* 按钮组宽度由内容决定，短线始终略长于按钮组并从同一左边缘开始。 */}
        <div className="mb-3 w-fit">
          <ViewToolbar activeView={activeView} onViewChange={handleViewChange} />
          <HorizontalEditorialDivider className="w-[calc(100%+0.75rem)]" />
        </div>

        <div
          className={
            'min-w-0 transition-opacity duration-150 ease-in-out motion-reduce:transition-none ' +
            (fillAvailableHeight ? 'flex min-h-0 flex-1 flex-col ' : '') +
            (viewFadingOut ? 'opacity-0' : 'opacity-100')
          }
        >
          {activeView === 'chat' ? (
            <ChatPanel
              poemId={activePoem.id}
              fillAvailableHeight={fillAvailableHeight}
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
              fillAvailableHeight={fillAvailableHeight}
              analysis={analysis}
              analyzing={analyzing}
              error={analysisError}
              limitNotice={analysisLimitNotice}
              onAnalyze={handleAnalyze}
              switching={!!switchTarget}
              animateResult={animatedAnalysisId !== activePoem.id}
              onAnimationStarted={() => setAnimatedAnalysisId(activePoem.id)}
              scrollTopRef={analysisScrollTopRef}
            />
          )}
        </div>
      </>
    )
  }

  function renderReaderContent() {
    if (poemReady) {
      return (
        <div className="w-full lg:flex lg:min-h-[var(--desktop-reading-stage-min-height)] lg:flex-col lg:pt-2">
          <PoemReader key={activePoem.id} work={activePoem} onSelect={handleReaderSelect} />
          {!wideDiscussionLayout && (
            <ReaderNavigation
              neighbors={neighbors}
              disabled={chatLoading || analyzing || !!switchTarget}
              onNavigate={handlePoemChange}
            />
          )}
        </div>
      )
    }

    return (
      <div
        role={detailError ? 'alert' : 'status'}
        className="min-h-155 rounded-md border border-border/60 bg-card px-8 py-12 text-sm text-muted-foreground"
      >
        {detailLoading
          ? '正在加载作品正文……'
          : detailError
            ? `作品加载失败：${detailError}`
            : '请从目录中选择作品'}

        {detailError && (
          <Button className="ml-3" type="button" variant="outline" size="sm" onClick={retryDetail}>
            重试
          </Button>
        )}
      </div>
    )
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
    )
  }

  const showReaderHeader = wideDiscussionLayout || !mobileDiscussionOpen

  return (
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-background text-foreground">
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
                  aria-label={catalogOpen ? '收起作品目录' : '展开作品目录'}
                  aria-controls="poem-catalog"
                  aria-expanded={catalogOpen}
                  onClick={() => setCatalogOpen((current) => !current)}
                >
                  <PanelLeft className="size-5" aria-hidden="true" />
                </Button>
                <span className="text-lg font-semibold tracking-tight">Poeticus</span>
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
                <span className="text-base font-semibold tracking-tight">阅读讨论</span>
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
              'absolute inset-0 z-10 bg-background ' +
              'md:transition-transform md:duration-[var(--motion-discussion-tablet-slide)] md:ease-[var(--motion-ease-settle)] ' +
              'motion-reduce:transition-none ' +
              (mobileDiscussionOpen ? 'md:-translate-x-full' : 'md:translate-x-0')
            }
          >
            {/* 给底部正文留出空间，避免被悬浮的讨论按钮遮挡。 */}
            <div
              className={
                'poeticus-scrollport poeticus-reader-scrollport h-full overflow-y-auto overscroll-contain px-5 pb-24 pt-7 md:px-8 ' +
                (readerHasContentAbove ? 'poeticus-scroll-fade-top ' : '') +
                (readerHasContentBelow ? 'poeticus-scroll-fade-bottom' : '')
              }
              ref={readerScrollRef}
              onScroll={(event) => handleReaderScroll(event.currentTarget)}
            >
              {switchError && (
                <div role="alert" className="mb-3 text-sm text-destructive">
                  作品切换失败：{switchError}。原作品仍可阅读，请重新选择。
                </div>
              )}

              <div className="relative min-w-0" aria-busy={!!switchTarget}>
                <div inert={!!switchTarget} className={poemTransitionClass}>
                  {renderReaderContent()}
                </div>
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
                aria-label={selected ? '打开讨论并使用已选诗句提问' : '打开阅读讨论'}
                onClick={openMobileDiscussion}
              >
                <MessageCircle className="size-4" aria-hidden="true" />
                <span>{selected ? '提问' : '对话'}</span>
                {hasUnreadReply && (
                  <span className="size-2 rounded-full bg-violet-300" aria-label="有新回复" />
                )}
              </Button>
            )}
          </section>

          <MobileDiscussionScreen open={mobileDiscussionOpen}>
            <div className="flex min-h-0 flex-1 flex-col">{renderDiscussionContent(true)}</div>
          </MobileDiscussionScreen>

          <div
            aria-hidden={!catalogOpen}
            inert={!catalogOpen}
            className={
              'absolute inset-0 z-40 transition-opacity duration-[var(--motion-catalog-phone-fade)] ' +
              'ease-[var(--motion-ease-settle)] motion-reduce:transition-none ' +
              'md:transition-none md:opacity-100 ' +
              (catalogOpen ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0')
            }
          >
            <button
              type="button"
              tabIndex={-1}
              aria-label="关闭作品目录遮罩"
              className={
                'absolute inset-0 bg-black/55 md:transition-opacity md:duration-[var(--motion-catalog-backdrop-fade)] ' +
                'md:ease-[var(--motion-ease-settle)] motion-reduce:transition-none ' +
                (catalogOpen
                  ? 'pointer-events-auto md:opacity-100'
                  : 'pointer-events-none md:opacity-0')
              }
              onClick={closeCatalog}
            />

            <div
              className={
                'relative h-full w-screen md:w-[min(88vw,420px)] ' +
                'md:transform md:transition-transform md:duration-[var(--motion-catalog-drawer-slide)] ' +
                'md:ease-[var(--motion-ease-settle)] motion-reduce:transition-none ' +
                (catalogOpen
                  ? 'pointer-events-auto md:translate-x-0'
                  : 'pointer-events-none md:-translate-x-full')
              }
            >
              {renderCatalog(catalogOpen)}
            </div>
          </div>
        </main>
      )}

      {wideDiscussionLayout && (
        <main className="mx-auto flex min-h-0 w-full max-w-[1600px] flex-1 flex-col overflow-hidden px-5 pb-7 pt-7 md:px-8">
          <div
            className={
              'grid h-full min-h-0 grid-cols-1 grid-rows-[minmax(0,1fr)] items-stretch gap-0 ' +
              '2xl:transition-[grid-template-columns] 2xl:duration-[var(--motion-catalog-grid-resize)] ' +
              '2xl:ease-[var(--motion-ease-settle)] motion-reduce:transition-none ' +
              (catalogOpen
                ? '2xl:grid-cols-[320px_minmax(0,1fr)]'
                : '2xl:grid-cols-[0px_minmax(0,1fr)]')
            }
          >
            <div
              inert={!catalogOpen}
              aria-hidden={!catalogOpen}
              className={
                'pointer-events-none fixed inset-0 z-50 2xl:relative 2xl:inset-auto 2xl:z-auto 2xl:h-full 2xl:min-h-0 ' +
                '2xl:min-w-0 2xl:overflow-hidden ' +
                (catalogOpen ? '2xl:border-r 2xl:border-border/60' : '2xl:border-r-0')
              }
            >
              <button
                type="button"
                tabIndex={-1}
                aria-label="关闭作品目录遮罩"
                className={
                  'absolute inset-0 bg-black/55 transition-opacity duration-[var(--motion-catalog-backdrop-fade)] ' +
                  'ease-[var(--motion-ease-settle)] motion-reduce:transition-none 2xl:hidden ' +
                  (catalogOpen
                    ? 'pointer-events-auto opacity-100'
                    : 'pointer-events-none opacity-0')
                }
                onClick={closeCatalog}
              />

              <div
                className={
                  'relative h-full w-screen md:w-[min(88vw,420px)] ' +
                  'transform transition-transform duration-[var(--motion-catalog-drawer-slide)] ' +
                  'ease-[var(--motion-ease-settle)] motion-reduce:transition-none ' +
                  '2xl:w-80 2xl:translate-x-0 2xl:pr-5 ' +
                  (catalogOpen
                    ? 'pointer-events-auto translate-x-0'
                    : 'pointer-events-none -translate-x-full')
                }
              >
                {renderCatalog(catalogOpen)}
              </div>
            </div>

            {/*
              右侧助手独立管理内容高度、分割线及按钮位置；
              目录收放时各栏随空间伸缩，阅读栏内部仍使用动态质心居中。
            */}
            <div
              className={'mx-auto h-full w-full min-h-0 min-w-0 max-w-[74rem] ' + (catalogOpen ? '2xl:pl-6' : '')}
            >
              <div className="relative h-full min-h-0 min-w-0" aria-busy={!!switchTarget}>
                {switchError && (
                  <div role="alert" className="mb-3 text-sm text-destructive">
                    作品切换失败：{switchError}。原作品仍可阅读，请重新选择。
                  </div>
                )}

                <div
                  inert={!!switchTarget}
                  className="grid h-full min-h-0 min-w-0 grid-cols-1 grid-rows-[minmax(0,1fr)] items-stretch gap-x-6 lg:grid-cols-[minmax(0,0.85fr)_minmax(340px,1.15fr)]"
                >
                  <div className="relative flex h-full min-h-0 min-w-0 flex-col">
                    <div
                      className={
                        'poeticus-scrollport poeticus-reader-scrollport flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto overscroll-contain pr-2 ' +
                        (readerHasContentAbove ? 'poeticus-scroll-fade-top ' : '') +
                        (readerHasContentBelow ? 'poeticus-scroll-fade-bottom' : '')
                      }
                      ref={readerScrollRef}
                      onScroll={(event) => handleReaderScroll(event.currentTarget)}
                    >
                      <div className={poemTransitionClass + ' lg:flex lg:flex-1 lg:flex-col'}>
                        {renderReaderContent()}
                      </div>
                    </div>
                    {poemReady && (
                      <ReaderNavigation
                        neighbors={neighbors}
                        disabled={chatLoading || analyzing || !!switchTarget}
                        onNavigate={handlePoemChange}
                      />
                    )}
                  </div>

                  <DesktopCompanionStage ready={poemReady}>
                    {renderDiscussionContent(false)}
                  </DesktopCompanionStage>
                </div>
              </div>
            </div>
          </div>
        </main>
      )}
    </div>
  )
}

export default App
