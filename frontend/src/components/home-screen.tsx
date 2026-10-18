import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'

import { ArrowRight } from 'lucide-react'
import { DailyRecommendation } from '@/components/daily-recommendation'
import { HorizontalEditorialDivider } from '@/components/editorial-divider'
import { HomeSearch } from '@/components/home-search'
import { Button } from '@/components/ui/button'
import { ThemeSwitcher } from '@/components/theme-switcher'
import { fetchPoem, fetchPoemPage } from '@/data/poem-library'
import type { Poem, PoemFilters, PoemPage } from '@/data/poem-library'
import { HOME_INITIAL_REVEAL_MS } from '@/lib/entrance-motion'
import { whenFontsReadyOrTimeout } from '@/lib/font-readiness'

type HomeScreenProps = {
  featured: Poem | null
  featuredLoading: boolean
  featuredError: string
  catalog: PoemPage | null
  filters: PoemFilters
  query: string
  loading: boolean
  error: string
  selectionBlocked: boolean
  onQueryChange: (value: string) => void
  onFiltersChange: (filters: PoemFilters) => void
  onSelect: (id: string) => void
  onEnterReader: () => void
}

// CSS 推荐区和分割线的延迟与搜索入口的 FLIP 位移共用这一时长。
const HOME_SEARCH_MOVE_DURATION_MS = 600
const HOME_RECOMMENDATION_FADE_OUT_MS = 330
const HOME_DIVIDER_FADE_OUT_MS = 130

// 仅本地开发显示：十个词牌分别从真实词库选择一首，便于直接比较竖排效果。
const HOME_PREVIEW_TUNES = [
  '杨柳枝',
  '菩萨蛮',
  '踏莎行',
  '水调歌头',
  '八声甘州',
  '戚氏',
  '临江仙',
  '鹧鸪天',
  '如梦令',
  '青玉案',
] as const

/** Home is an entry to the existing Reader; it never owns a second conversation. */
export function HomeScreen({
  featured,
  featuredLoading,
  featuredError,
  catalog,
  filters,
  query,
  loading,
  error,
  selectionBlocked,
  onQueryChange,
  onFiltersChange,
  onSelect,
  onEnterReader,
}: HomeScreenProps) {
  const mainRef = useRef<HTMLElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLDivElement>(null)
  const [mobileBodyMaxHeight, setMobileBodyMaxHeight] = useState<number | null>(null)
  const [outgoing, setOutgoing] = useState<{
    recommendation: DOMRect
    divider: DOMRect
  } | null>(null)
  const searchBeforeLayoutRef = useRef<DOMRect | null>(null)
  const [returnPhase, setReturnPhase] = useState<'none' | 'waiting' | 'revealing'>('none')
  // HomeScreen remounts on each entry from Reader. Replay only on page entry,
  // not when resizing, focusing search, or changing the theme.
  const [initialEntrance, setInitialEntrance] = useState<'waiting' | 'revealing' | 'done'>(() =>
    !filters.q?.trim() && !window.matchMedia('(prefers-reduced-motion: reduce)').matches
      ? 'waiting'
      : 'done',
  )
  const [entranceCompleted, setEntranceCompleted] = useState(false)
  const [previewTune, setPreviewTune] = useState<string | null>(null)
  const [previewPoem, setPreviewPoem] = useState<Poem | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState('')
  const revealTimerRef = useRef<number | null>(null)
  const hasSearch = !!filters.q?.trim()

  useEffect(
    () => () => {
      if (revealTimerRef.current !== null) window.clearTimeout(revealTimerRef.current)
    },
    [],
  )

  // 开发用排版样本：按词牌读取一首馆藏真词，只覆盖首页预览，不影响每日推荐数据。
  useEffect(() => {
    if (!import.meta.env.DEV || !previewTune) return
    const controller = new AbortController()
    const loadPreview = async () => {
      try {
        const page = await fetchPoemPage(
          { cipai: previewTune, limit: 1, offset: 0 },
          controller.signal,
        )
        if (!page.items.length) throw new Error(`词库中没有找到「${previewTune}」`)
        const poem = await fetchPoem(page.items[0].id, controller.signal)
        if (!controller.signal.aborted) setPreviewPoem(poem)
      } catch (cause: unknown) {
        if (!controller.signal.aborted) {
          setPreviewError(cause instanceof Error ? cause.message : '样本加载失败')
        }
      } finally {
        if (!controller.signal.aborted) setPreviewLoading(false)
      }
    }
    void loadPreview()
    return () => controller.abort()
  }, [previewTune])

  // 每次进入首页都等推荐数据与字体就绪、浏览器完成两帧布局后才入场。
  useEffect(() => {
    if (initialEntrance !== 'waiting' || !!filters.q?.trim()) return
    if (!featured || featuredError) return
    let disposed = false
    let firstFrame = 0
    let secondFrame = 0
    const cancelFontWait = whenFontsReadyOrTimeout(() => {
      if (disposed) return
      firstFrame = window.requestAnimationFrame(() => {
        secondFrame = window.requestAnimationFrame(() => {
          if (disposed) return
          setInitialEntrance('revealing')
        })
      })
    })
    return () => {
      disposed = true
      cancelFontWait()
      window.cancelAnimationFrame(firstFrame)
      window.cancelAnimationFrame(secondFrame)
    }
  }, [initialEntrance, featured, featuredLoading, featuredError, filters.q])

  useEffect(() => {
    if (initialEntrance !== 'revealing') return
    const timer = window.setTimeout(() => {
      setInitialEntrance('done')
      setEntranceCompleted(true)
    }, HOME_INITIAL_REVEAL_MS)
    return () => window.clearTimeout(timer)
  }, [initialEntrance])

  // 切换权威搜索状态的同时保留旧推荐的退出画面；它脱离文档流后，搜索框立刻可以上移。
  function changeHomeFilters(next: PoemFilters) {
    if (revealTimerRef.current !== null) {
      window.clearTimeout(revealTimerRef.current)
      revealTimerRef.current = null
    }
    const nextHasSearch = !!next.q?.trim()
    if (nextHasSearch === hasSearch) {
      onFiltersChange(next)
      return
    }

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const search = searchRef.current?.querySelector<HTMLElement>('[aria-label="馆藏搜索"]')
    searchBeforeLayoutRef.current = reducedMotion ? null : (search?.getBoundingClientRect() ?? null)

    if (nextHasSearch && !reducedMotion) {
      const recommendation = mainRef.current?.querySelector<HTMLElement>(
        '[data-home-recommendation-slot]',
      )
      const divider = mainRef.current?.querySelector<HTMLElement>('.home-recommendation-divider')
      setOutgoing(
        recommendation && divider
          ? {
              recommendation: recommendation.getBoundingClientRect(),
              divider: divider.getBoundingClientRect(),
            }
          : null,
      )
    } else {
      setOutgoing(null)
    }
    setReturnPhase(!nextHasSearch && !reducedMotion ? 'waiting' : 'none')
    onFiltersChange(next)
  }

  // 直接量取搜索区与推荐区之间的实际占位，避免 Safari 的浏览器栏缩小时压掉正文字高。
  useLayoutEffect(() => {
    const main = mainRef.current
    const content = contentRef.current
    const search = searchRef.current
    if (!main || !content || !search) return

    const measure = () => {
      if (window.matchMedia('(min-width: 64rem)').matches) return
      const slot = main.querySelector<HTMLElement>('[data-home-recommendation-slot]')
      if (!slot) return
      // 搜索区的位置由布局决定；推荐词只使用上方独立槽位的高度预算。
      // 不再用正文自身高度反推剩余空间，避免测量随换列结果反复变化。
      const available = Math.max(192, Math.floor(slot.clientHeight - 12))
      setMobileBodyMaxHeight((previous) => (previous === available ? previous : available))
    }

    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(main)
    observer.observe(search)
    const slot = main.querySelector<HTMLElement>('[data-home-recommendation-slot]')
    if (slot) observer.observe(slot)
    window.addEventListener('resize', measure)
    window.visualViewport?.addEventListener('resize', measure)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', measure)
      window.visualViewport?.removeEventListener('resize', measure)
    }
  }, [featured, hasSearch])

  // 记录旧位置、渲染新布局、再反向位移（FLIP）。恢复推荐的时机由实际几何关系决定。
  useLayoutEffect(() => {
    const main = mainRef.current
    if (main) main.scrollTop = 0
    const before = searchBeforeLayoutRef.current
    searchBeforeLayoutRef.current = null
    if (!before) return
    const search = searchRef.current?.querySelector<HTMLElement>('[aria-label="馆藏搜索"]')
    if (!search) return
    const after = search.getBoundingClientRect()
    const deltaY = before.top - after.top
    const deltaX = before.left - after.left
    search.getAnimations().forEach((animation) => animation.cancel())
    if (Math.abs(deltaY) < 1 && Math.abs(deltaX) < 1) return
    const move = search.animate(
      [{ transform: `translate(${deltaX}px, ${deltaY}px)` }, { transform: 'translate(0, 0)' }],
      {
        duration: HOME_SEARCH_MOVE_DURATION_MS,
        delay: hasSearch ? 60 : 0,
        fill: 'backwards',
        easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
      },
    )
    if (hasSearch) return

    let frame = 0
    const reveal = () => {
      setReturnPhase('revealing')
      // 入场结束后撤下动画 class，改变窗口尺寸不会让文字列重播。
      revealTimerRef.current = window.setTimeout(() => {
        setReturnPhase('none')
        revealTimerRef.current = null
      }, 750)
    }
    const revealIfClear = () => {
      const poem = mainRef.current?.querySelector<HTMLElement>(
        '[data-home-recommendation-slot] .home-featured-poem',
      )
      const poemBottom = poem?.getBoundingClientRect().bottom ?? -Infinity
      // 搜索框真正离开诗文区后才开始揭示；短词、长词及不同视口共用此判定。
      if (search.getBoundingClientRect().top >= poemBottom + 8 || move.playState === 'finished') {
        reveal()
      } else {
        frame = window.requestAnimationFrame(revealIfClear)
      }
    }
    frame = window.requestAnimationFrame(revealIfClear)
    return () => window.cancelAnimationFrame(frame)
  }, [hasSearch])

  const previewFeatured = import.meta.env.DEV && previewTune && previewPoem ? previewPoem : featured
  const hasRecommendation = !hasSearch || outgoing !== null
  const recommendationIsReturning = !hasSearch && returnPhase !== 'none'
  const homeInitialWaiting = initialEntrance === 'waiting' && !!featured && !hasSearch
  const homeInitialRevealing = initialEntrance === 'revealing' && !hasSearch
  // Unavailable recommendations must never leave the search entry inaccessible.
  const searchAwaitsEntrance =
    !hasSearch &&
    !featuredError &&
    (featuredLoading || !!featured) &&
    (initialEntrance === 'waiting' || initialEntrance === 'revealing')
  const outStyle = (rect: DOMRect): CSSProperties => ({
    position: 'fixed',
    left: rect.left,
    top: rect.top,
    width: rect.width,
    height: rect.height,
    zIndex: 1,
    pointerEvents: 'none',
  })

  return (
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-background text-foreground">
      <header className="shrink-0 border-b border-border/50">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-2 px-3 py-4 sm:px-5 md:px-8">
          <span className="text-base font-semibold tracking-tight sm:text-lg">Poeticus</span>
          <div className="flex items-center gap-1 sm:gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={onEnterReader}>
              阅读室 <ArrowRight className="size-4 max-[359px]:hidden" aria-hidden="true" />
            </Button>
            <ThemeSwitcher />
          </div>
        </div>
      </header>
      <main
        id="home"
        ref={mainRef}
        className="poeticus-scrollport min-h-0 flex-1 overflow-y-auto overscroll-contain"
        style={
          {
            '--home-classic-max-height': mobileBodyMaxHeight ? `${mobileBodyMaxHeight}px` : '18rem',
            '--home-search-move-duration': `${HOME_SEARCH_MOVE_DURATION_MS}ms`,
            '--home-recommendation-fade-duration': `${HOME_RECOMMENDATION_FADE_OUT_MS}ms`,
            '--home-divider-fade-duration': `${HOME_DIVIDER_FADE_OUT_MS}ms`,
          } as CSSProperties
        }
      >
        <div
          ref={contentRef}
          className={
            hasSearch
              ? 'mx-auto flex min-h-full w-full max-w-6xl flex-col px-5 pt-8 pb-8 md:px-8 lg:pt-14'
              : 'mx-auto flex min-h-full w-full max-w-6xl flex-col justify-start px-5 pt-6 pb-4 md:px-8 lg:justify-center lg:pt-10 lg:pb-[6.5rem]'
          }
        >
          {/* 父容器统一管理推荐区、分割线和搜索区的间距；剩余高度只交给推荐区。 */}
          <div
            className={
              hasSearch
                ? 'flex flex-col gap-8 lg:gap-10'
                : 'flex min-h-0 flex-1 flex-col gap-4 lg:flex-none lg:gap-10'
            }
          >
            {hasRecommendation && (
              <div
                data-home-recommendation-slot
                style={outgoing && hasSearch ? outStyle(outgoing.recommendation) : undefined}
                onAnimationEnd={(event) => {
                  if (outgoing && event.target === event.currentTarget) setOutgoing(null)
                }}
                className={
                  'flex min-h-0 w-full flex-1 flex-col justify-center lg:block lg:flex-none ' +
                  (outgoing && hasSearch
                    ? 'home-recommendation-exiting'
                    : returnPhase === 'waiting' || homeInitialWaiting
                      ? 'pointer-events-none opacity-0'
                      : returnPhase === 'revealing'
                        ? 'home-recommendation-revealing'
                        : homeInitialRevealing
                          ? 'home-recommendation-revealing home-recommendation-initial'
                          : '')
                }
              >
                <DailyRecommendation
                  poem={previewFeatured}
                  loading={featuredLoading}
                  error={featuredError}
                  disabled={selectionBlocked}
                  onRead={onSelect}
                />
              </div>
            )}
            {hasRecommendation && (
              <HorizontalEditorialDivider
                style={outgoing && hasSearch ? outStyle(outgoing.divider) : undefined}
                className={
                  'home-recommendation-divider mx-auto w-full max-w-2xl ' +
                  (outgoing && hasSearch
                    ? 'home-divider-exiting'
                    : recommendationIsReturning
                      ? returnPhase === 'revealing'
                        ? 'home-divider-growing'
                        : 'opacity-0'
                      : homeInitialWaiting
                        ? 'opacity-0'
                        : homeInitialRevealing
                          ? 'home-divider-growing home-divider-initial'
                          : '')
                }
              />
            )}
            <div
              ref={searchRef}
              data-home-search-slot
              inert={searchAwaitsEntrance}
              className={
                'w-full shrink-0 ' +
                (searchAwaitsEntrance
                  ? 'pointer-events-none opacity-0'
                  : entranceCompleted
                    ? 'home-search-intro-revealing'
                    : '')
              }
            >
              <HomeSearch
                catalog={catalog}
                filters={filters}
                query={query}
                loading={loading}
                error={error}
                disabled={selectionBlocked}
                onQueryChange={onQueryChange}
                onFiltersChange={changeHomeFilters}
                onSelect={onSelect}
              />
            </div>
          </div>
        </div>
      </main>
      {import.meta.env.DEV && !hasSearch && (
        <aside
          aria-label="首页竖排调试样本"
          className="fixed right-4 bottom-4 z-50 hidden w-[420px] max-w-[calc(100vw-2rem)] rounded-lg border border-border/70 bg-background/95 p-3 shadow-md backdrop-blur-sm lg:block"
        >
          <div className="mb-2 flex items-center justify-between gap-2 text-xs text-muted-foreground">
            <span>本地排版样本 · 十个词牌</span>
            <button
              type="button"
              className="rounded px-2 py-1 hover:bg-muted"
              onClick={() => {
                setPreviewTune(null)
                setPreviewPoem(null)
                setPreviewError('')
                setPreviewLoading(false)
              }}
            >
              恢复今日推荐
            </button>
          </div>
          <div className="grid grid-cols-5 gap-1.5">
            {HOME_PREVIEW_TUNES.map((tune) => (
              <button
                key={tune}
                type="button"
                aria-pressed={previewTune === tune}
                className={`rounded border px-1 py-1.5 text-xs transition-colors ${
                  previewTune === tune
                    ? 'border-[#AA381E] text-[#AA381E]'
                    : 'border-border/60 hover:bg-muted'
                }`}
                onClick={() => {
                  if (previewTune === tune) return
                  setPreviewPoem(null)
                  setPreviewError('')
                  setPreviewLoading(true)
                  setPreviewTune(tune)
                }}
              >
                {tune}
              </button>
            ))}
          </div>
          {(previewLoading || previewError) && (
            <p role="status" className="mt-2 text-xs text-muted-foreground">
              {previewLoading ? '正在加载馆藏作品…' : previewError}
            </p>
          )}
        </aside>
      )}
    </div>
  )
}
