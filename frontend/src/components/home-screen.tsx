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
  const searchRef = useRef<HTMLDivElement>(null)
  const [mobileBodyMaxHeight, setMobileBodyMaxHeight] = useState<number | null>(null)

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
          className="mx-auto flex min-h-full w-full max-w-6xl flex-col justify-start px-5 pt-6 pb-4 md:px-8 lg:justify-center lg:pt-10 lg:pb-[6.5rem]"
        >
          {/* 父容器统一管理推荐区、分割线和搜索区的间距；剩余高度只交给推荐区。 */}
          <div className="flex min-h-0 flex-1 flex-col gap-4 lg:flex-none lg:gap-10">
            <div
              data-home-recommendation-slot
              className="flex min-h-0 w-full flex-1 flex-col justify-center lg:block lg:flex-none"
            >
              <DailyRecommendation
                poem={featured}
                loading={featuredLoading}
                error={featuredError}
                disabled={selectionBlocked}
                onRead={onSelect}
              />
            </div>
            <HorizontalEditorialDivider className="mx-auto w-full max-w-2xl" />
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
