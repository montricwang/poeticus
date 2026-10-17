import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'

import { ArrowRight } from 'lucide-react'
import { Popover } from 'radix-ui'
import { DailyRecommendation } from '@/components/daily-recommendation'
import { HorizontalEditorialDivider } from '@/components/editorial-divider'
import { HomeSearch } from '@/components/home-search'
import { Button } from '@/components/ui/button'
import { ThemeSwitcher } from '@/components/theme-switcher'
import { HOME_DEBUG_POEMS } from '@/lib/home-debug-poems'
import { fetchPoem } from '@/data/poem-library'
import type { Poem, PoemFilters, PoemPage } from '@/data/poem-library'

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
  const [debugOpen, setDebugOpen] = useState(false)
  const [debugSampleId, setDebugSampleId] = useState<string | null>(null)
  const [debugPoem, setDebugPoem] = useState<Poem | null>(null)
  const [debugError, setDebugError] = useState('')
  const hasSearch = !!filters.q?.trim()

  // 调试样本只替换首页展示内容，不修改当天推荐，也不触碰阅读器状态。
  useEffect(() => {
    if (!import.meta.env.DEV || !debugSampleId) return
    const controller = new AbortController()
    void fetchPoem(debugSampleId, controller.signal)
      .then((poem) => {
        if (!controller.signal.aborted) setDebugPoem(poem)
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted)
          setDebugError(cause instanceof Error ? cause.message : '调试词作加载失败')
      })
    return () => controller.abort()
  }, [debugSampleId])

  const debugging = import.meta.env.DEV && debugSampleId !== null
  const visiblePoem = debugging ? (debugPoem?.id === debugSampleId ? debugPoem : null) : featured
  const visibleError = debugging ? debugError : featuredError
  const visibleLoading = debugging ? !visiblePoem && !debugError : featuredLoading

  function selectDebugSample(id: string | null) {
    setDebugSampleId(id)
    setDebugPoem(null)
    setDebugError('')
    setDebugOpen(false)
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
  }, [visiblePoem, hasSearch])

  // 模式切换后从顶部展示搜索入口；不让旧的搜索结果滚动位置留下来。
  useLayoutEffect(() => {
    if (mainRef.current) mainRef.current.scrollTop = 0
  }, [hasSearch])

  return (
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-background text-foreground">
      <header className="shrink-0 border-b border-border/50">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-2 px-3 py-4 sm:px-5 md:px-8">
          <span className="text-base font-semibold tracking-tight sm:text-lg">Poeticus</span>
          <div className="flex items-center gap-1 sm:gap-2">
            {import.meta.env.DEV && (
              <Popover.Root open={debugOpen} onOpenChange={setDebugOpen}>
                <Popover.Trigger asChild>
                  <Button type="button" variant="ghost" size="sm" aria-label="首页词牌排版调试">
                    调试
                  </Button>
                </Popover.Trigger>
                <Popover.Portal>
                  <Popover.Content
                    align="end"
                    sideOffset={8}
                    className="z-50 max-h-[70dvh] w-44 overflow-y-auto rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-md outline-none"
                    aria-label="切换首页推荐词牌"
                  >
                    <button
                      type="button"
                      aria-pressed={debugSampleId === null}
                      onClick={() => selectDebugSample(null)}
                      className="w-full rounded-sm px-3 py-2 text-left text-sm hover:bg-muted aria-pressed:font-semibold"
                    >
                      今日推荐
                    </button>
                    <div className="my-1 h-px bg-border" />
                    {HOME_DEBUG_POEMS.map((sample) => (
                      <button
                        key={sample.id}
                        type="button"
                        aria-pressed={debugSampleId === sample.id}
                        onClick={() => selectDebugSample(sample.id)}
                        className="flex w-full items-baseline justify-between gap-2 rounded-sm px-3 py-2 text-left text-sm hover:bg-muted aria-pressed:font-semibold"
                      >
                        <span>{sample.tune}</span>
                        <span className="text-xs text-muted-foreground">{sample.author}</span>
                      </button>
                    ))}
                  </Popover.Content>
                </Popover.Portal>
              </Popover.Root>
            )}
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
            {!hasSearch && (
              <div
                data-home-recommendation-slot
                className="flex min-h-0 w-full flex-1 flex-col justify-center lg:block lg:flex-none"
              >
                <DailyRecommendation
                  poem={visiblePoem}
                  loading={visibleLoading}
                  error={visibleError}
                  disabled={selectionBlocked}
                  onRead={onSelect}
                />
              </div>
            )}
            {!hasSearch && <HorizontalEditorialDivider className="mx-auto w-full max-w-2xl" />}
            <div ref={searchRef} className="w-full shrink-0">
              <HomeSearch
                catalog={catalog}
                filters={filters}
                query={query}
                loading={loading}
                error={error}
                disabled={selectionBlocked}
                onQueryChange={onQueryChange}
                onFiltersChange={onFiltersChange}
                onSelect={onSelect}
              />
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
