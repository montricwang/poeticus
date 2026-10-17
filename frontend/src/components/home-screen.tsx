import { useLayoutEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'

import { ArrowRight } from 'lucide-react'
import { DailyRecommendation } from '@/components/daily-recommendation'
import { HorizontalEditorialDivider } from '@/components/editorial-divider'
import { HomeSearch } from '@/components/home-search'
import { Button } from '@/components/ui/button'
import { ThemeSwitcher } from '@/components/theme-switcher'
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
  const searchRef = useRef<HTMLElement>(null)
  const [mobileBodyMaxHeight, setMobileBodyMaxHeight] = useState<number | null>(null)

  // 仅测量固定搜索入口；结果列表可滚动，不应反过来缩短上方推荐词。
  useLayoutEffect(() => {
    const main = mainRef.current
    const content = contentRef.current
    const search = searchRef.current
    if (!main || !content || !search) return

    const measure = () => {
      if (window.matchMedia('(min-width: 64rem)').matches) return
      const body = main.querySelector<HTMLElement>('.home-classic-body')
      if (!body) return
      const bodyRect = body.getBoundingClientRect()
      if (!bodyRect.height) return
      const mainRect = main.getBoundingClientRect()
      const searchRect = search.getBoundingClientRect()
      const spaceBeforeBody = bodyRect.top - mainRect.top + main.scrollTop
      const spaceAfterBody = searchRect.bottom - bodyRect.bottom
      const bottomPadding = Number.parseFloat(getComputedStyle(content).paddingBottom) || 0
      // 视口太矮时允许首页纵向滚动，不把长词压成每列只有几字的密集短列。
      const available = Math.max(
        288,
        Math.floor(main.clientHeight - spaceBeforeBody - spaceAfterBody - bottomPadding - 8),
      )
      setMobileBodyMaxHeight((previous) => (previous === available ? previous : available))
    }

    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(main)
    observer.observe(search)
    window.addEventListener('resize', measure)
    window.visualViewport?.addEventListener('resize', measure)
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', measure)
      window.visualViewport?.removeEventListener('resize', measure)
    }
  }, [featured])

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
          } as CSSProperties
        }
      >
        <div
          ref={contentRef}
          className="mx-auto flex min-h-full w-full max-w-6xl flex-col justify-start px-5 pt-6 pb-6 md:px-8 lg:justify-center lg:pt-10 lg:pb-[6.5rem]"
        >
          {/* 手机靠上排，桌面仍整体居中；内容超出视口时由 main 滚动。 */}
          <div className="lg:flex lg:flex-col lg:gap-10">
            <DailyRecommendation
              poem={featured}
              loading={featuredLoading}
              error={featuredError}
              disabled={selectionBlocked}
              onRead={onSelect}
            />
            <HorizontalEditorialDivider className="mx-auto my-6 w-full max-w-2xl lg:my-0" />
            <div className="w-full">
              <HomeSearch
                searchSectionRef={searchRef}
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
