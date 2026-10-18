import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { PoemReader } from '@/components/poem-reader'
import { ReaderNavigation } from '@/components/reader-navigation'
import { PoemCatalog } from '@/components/poem-catalog'
import { MobileLayout } from '@/components/mobile-layout'
import { DesktopLayout } from '@/components/desktop-layout'
import { HomeScreen } from '@/components/home-screen'
import { ChatPanel } from '@/components/chat-panel'
import { AnalysisPanel } from '@/components/analysis-panel'
import { CompanionPane } from '@/components/companion-pane'
import type { ActiveView } from '@/components/view-toolbar'

import { fetchPoem } from '@/data/poem-library'
import { usePoemCatalog } from '@/hooks/use-poem-catalog'
import { usePoemDetail } from '@/hooks/use-poem-detail'
import { usePoemNeighbors } from '@/hooks/use-poem-neighbors'
import { useAutoHideScrollbars } from '@/hooks/use-auto-hide-scrollbars'
import { useConversationPersistence } from '@/hooks/use-conversation-persistence'
import { usePoemAnalysis } from '@/hooks/use-poem-analysis'
import { loadInitialChatState } from '@/lib/chat-initial-state'
import { motionDurationMs } from '@/lib/motion'
import { READER_INITIAL_REVEAL_MS } from '@/lib/entrance-motion'
import { whenFontsReadyOrTimeout } from '@/lib/font-readiness'
import { WIDE_DISCUSSION_MEDIA } from '@/lib/responsive-layout'
import { useChatSession } from '@/hooks/use-chat-session'
import { useFeaturedPoem } from '@/hooks/use-featured-poem'

import type { SelectedText } from '@/types/poem'

/** 组装目录、阅读器、聊天和赏析；跨作品切换由此协调。 */
function App() {
  // --- 1. 初始化作品、目录及会话状态 ---
  const [screen, setScreen] = useState<'home' | 'reader'>(() =>
    window.location.hash === '#reader' ? 'reader' : 'home',
  )
  const [readerEntrance, setReaderEntrance] = useState<'waiting' | 'revealing' | 'done'>(() =>
    window.location.hash === '#reader' &&
    !window.matchMedia('(prefers-reduced-motion: reduce)').matches
      ? 'waiting'
      : 'done',
  )
  const { featured, loading: featuredLoading, error: featuredError } = useFeaturedPoem()
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

  // 1024px 起使用固定双栏。目录默认关闭，并始终占用右侧辅助栏。
  const [catalogOpen, setCatalogOpen] = useState(false)
  const [wideDiscussionLayout, setWideDiscussionLayout] = useState(
    () => window.matchMedia(WIDE_DISCUSSION_MEDIA).matches,
  )
  const [mobileDiscussionOpen, setMobileDiscussionOpen] = useState(false)
  useAutoHideScrollbars()
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
    const followHistory = () => {
      const next = window.location.hash === '#reader' ? 'reader' : 'home'
      setScreen(next)
      setReaderEntrance(
        next === 'reader' && !window.matchMedia('(prefers-reduced-motion: reduce)').matches
          ? 'waiting'
          : 'done',
      )
    }
    window.addEventListener('popstate', followHistory)
    window.addEventListener('hashchange', followHistory)
    return () => {
      window.removeEventListener('popstate', followHistory)
      window.removeEventListener('hashchange', followHistory)
    }
  }, [])

  function navigateTo(next: 'home' | 'reader') {
    const hash = next === 'reader' ? '#reader' : ''
    if (window.location.hash !== hash) {
      window.history.pushState(null, '', window.location.pathname + window.location.search + hash)
    }
    setScreen(next)
    setReaderEntrance(
      next === 'reader' && !window.matchMedia('(prefers-reduced-motion: reduce)').matches
        ? 'waiting'
        : 'done',
    )
    if (next === 'home') {
      setCatalogOpen(false)
      setMobileDiscussionOpen(false)
    }
  }

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
  }, [activePoem, poemId, screen, wideDiscussionLayout, updateReaderScrollEdges])

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
    }, motionDurationMs('--motion-view-fade'))
  }

  /** 切换作品时协调预取、过渡动画和旧会话保存。 */
  function handlePoemChange(nextId: string) {
    if (inFlightRef.current || analyzing || !nextId || nextId === poemId) return
    if (screen === 'reader' && readerEntrance !== 'waiting') setReaderEntrance('done')

    switchControllerRef.current?.abort()
    const controller = new AbortController()
    switchControllerRef.current = controller
    setSwitchTarget(nextId)
    setSwitchError('')

    const animateSwap =
      screen === 'reader' && !window.matchMedia('(prefers-reduced-motion: reduce)').matches

    void fetchPoem(nextId, controller.signal)
      .then(async (work) => {
        if (controller.signal.aborted) return

        // 等待网络请求时保持旧作品可见；取得新作品后才开始淡出。
        if (animateSwap) {
          setPoemSwapPhase('leaving')
          await new Promise<void>((resolve) =>
            window.setTimeout(resolve, motionDurationMs('--motion-poem-swap')),
          )
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

        // 桌面目录支持连续选诗；移动端选中作品后仍收起抽屉。
        if (!wideDiscussionLayout && catalogOpen) closeCatalog()

        if (animateSwap) {
          // 在页面隐藏期间更新作品、消息、输入区和引用内容；
          // 留出两帧供 React 绘制及伴读区重新测量布局。
          setPoemSwapPhase('arriving')
          await new Promise<void>((resolve) => {
            window.requestAnimationFrame(() => window.requestAnimationFrame(() => resolve()))
          })
          if (controller.signal.aborted) return
          setPoemSwapPhase('steady')
          await new Promise<void>((resolve) =>
            window.setTimeout(resolve, motionDurationMs('--motion-poem-swap')),
          )
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
  // 阅读室首次进入只对目标诗文入场；切换作品不重新逐行展开。
  useEffect(() => {
    if (screen !== 'reader' || readerEntrance !== 'waiting' || !poemReady) return
    if (switchTarget || poemSwapPhase !== 'steady') return
    let disposed = false
    let frameOne = 0
    let frameTwo = 0
    const cancelFontWait = whenFontsReadyOrTimeout(() => {
      if (disposed) return
      frameOne = window.requestAnimationFrame(() => {
        frameTwo = window.requestAnimationFrame(() => {
          if (!disposed) setReaderEntrance('revealing')
        })
      })
    })
    return () => {
      disposed = true
      cancelFontWait()
      window.cancelAnimationFrame(frameOne)
      window.cancelAnimationFrame(frameTwo)
    }
  }, [screen, readerEntrance, poemReady, switchTarget, poemSwapPhase])

  useEffect(() => {
    if (readerEntrance !== 'revealing') return
    const timer = window.setTimeout(() => setReaderEntrance('done'), READER_INITIAL_REVEAL_MS)
    return () => window.clearTimeout(timer)
  }, [readerEntrance])

  // 请求新作品期间保留旧内容，阅读区和伴读区共用切换阶段。
  const poemTransitionClass =
    'transition-[opacity,transform] duration-[var(--motion-poem-swap)] ease-[var(--motion-ease-settle)] motion-reduce:transition-none ' +
    (poemSwapPhase === 'leaving'
      ? '-translate-y-1 opacity-0'
      : poemSwapPhase === 'arriving'
        ? 'translate-y-1 opacity-0'
        : 'translate-y-0 opacity-100')

  function handleReaderScroll(element: HTMLDivElement) {
    updateReaderScrollEdges(element)
  }

  /** 根据当前视图组装聊天或赏析面板，供不同屏幕布局共用。 */
  function renderDiscussionContent(fillAvailableHeight: boolean) {
    if (!poemReady) {
      return (
        <div className="flex h-165 items-center justify-center rounded-md border border-border/60 bg-card text-sm text-muted-foreground">
          加载作品后，即可开始阅读与 AI 讨论。
        </div>
      )
    }

    return (
      <CompanionPane
        activeView={activeView}
        onViewChange={handleViewChange}
        fillAvailableHeight={fillAvailableHeight}
        fadingOut={viewFadingOut}
      >
        {activeView === 'chat' ? (
          <ChatPanel
            poemId={activePoem.id}
            swapPhase={poemSwapPhase}
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
      </CompanionPane>
    )
  }

  /** 组装作品阅读区及前后篇导航。 */
  function renderReaderContent() {
    if (poemReady) {
      return (
        <div className="w-full lg:flex lg:min-h-0 lg:flex-1 lg:flex-col lg:pt-2">
          <PoemReader
            key={activePoem.id}
            work={activePoem}
            onSelect={handleReaderSelect}
            selected={selected}
            entrance={readerEntrance}
          />
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

  function handleCatalogSelection(nextId: string) {
    if (nextId !== poemId) handlePoemChange(nextId)
    // 桌面目录可连续浏览，只有移动端选中作品后返回阅读。
    if (!wideDiscussionLayout) closeCatalog()
  }

  function renderCatalog(open: boolean, embedded = false) {
    return (
      <PoemCatalog
        embedded={embedded}
        catalog={catalog}
        filters={filters}
        query={searchInput}
        loading={catalogLoading}
        error={catalogError}
        activePoemId={poemId}
        selectionBlocked={chatLoading || analyzing || !!switchTarget}
        onQueryChange={setSearchInput}
        onFiltersChange={updateCatalogFilters}
        onSelect={handleCatalogSelection}
        onClose={closeCatalog}
        open={open}
      />
    )
  }

  function openHomePoem(id: string) {
    if (chatLoading || analyzing || !!switchTarget) return
    if (id !== poemId) handlePoemChange(id)
    navigateTo('reader')
  }

  if (screen === 'home') {
    return (
      <HomeScreen
        featured={featured}
        featuredLoading={featuredLoading}
        featuredError={featuredError}
        catalog={catalog}
        filters={filters}
        query={searchInput}
        loading={catalogLoading}
        error={catalogError}
        selectionBlocked={chatLoading || analyzing || !!switchTarget}
        onQueryChange={setSearchInput}
        onFiltersChange={updateCatalogFilters}
        onSelect={openHomePoem}
        onEnterReader={() => navigateTo('reader')}
      />
    )
  }

  const catalogLayout = {
    open: catalogOpen,
    content: renderCatalog(catalogOpen, wideDiscussionLayout),
    onToggle: () => setCatalogOpen((current) => !current),
    onClose: closeCatalog,
  }
  const readerLayout = {
    content: renderReaderContent(),
    onScroll: handleReaderScroll,
    hasContentAbove: readerHasContentAbove,
    hasContentBelow: readerHasContentBelow,
    ready: poemReady,
    switching: !!switchTarget,
    switchError,
    transitionClass: poemTransitionClass,
  }

  return (
    <div
      className={
        'flex h-dvh min-h-0 flex-col overflow-hidden bg-background text-foreground ' +
        (readerEntrance === 'revealing' ? 'reader-screen-entering' : '')
      }
    >
      {wideDiscussionLayout ? (
        <DesktopLayout
          catalog={catalogLayout}
          reader={readerLayout}
          onGoHome={() => navigateTo('home')}
          catalogToggleRef={catalogToggleRef}
          readerScrollRef={readerScrollRef}
          discussion={renderDiscussionContent(false)}
          navigation={
            poemReady ? (
              <ReaderNavigation
                embedded
                neighbors={neighbors}
                disabled={chatLoading || analyzing || !!switchTarget}
                onNavigate={handlePoemChange}
              />
            ) : null
          }
          idle={activeView === 'chat' ? turns.length === 0 : !analysis}
          swapPhase={poemSwapPhase}
        />
      ) : (
        <MobileLayout
          catalog={catalogLayout}
          reader={readerLayout}
          onGoHome={() => navigateTo('home')}
          catalogToggleRef={catalogToggleRef}
          readerScrollRef={readerScrollRef}
          discussion={{
            content: renderDiscussionContent(true),
            open: mobileDiscussionOpen,
            onOpen: openMobileDiscussion,
            onClose: closeMobileDiscussion,
            hasSelection: !!selected,
            hasUnreadReply,
          }}
        />
      )}
    </div>
  )
}

export default App
