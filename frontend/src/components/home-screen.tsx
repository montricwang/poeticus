import { useLayoutEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'

import { ArrowRight, ChevronDown } from 'lucide-react'
import { Popover } from 'radix-ui'
import { DailyRecommendation } from '@/components/daily-recommendation'
import { HorizontalEditorialDivider } from '@/components/editorial-divider'
import { HomeSearch } from '@/components/home-search'
import { Button } from '@/components/ui/button'
import { ThemeSwitcher } from '@/components/theme-switcher'
import type { Poem, PoemFilters, PoemPage } from '@/data/poem-library'
import { PREVIEW_POEMS } from '@/hooks/use-featured-poem'

type HomeScreenProps = {
  featured: Poem | null
  featuredLoading: boolean
  featuredError: string
  previewPoemId: string
  onPreviewPoemChange: (id: string) => void
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
  previewPoemId,
  onPreviewPoemChange,
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
      const body = main.querySelector<HTMLElement>('.home-classic-body')
      if (!body) return
      const bodyRect = body.getBoundingClientRect()
      if (!bodyRect.height) return
      const mainRect = main.getBoundingClientRect()
      const searchRect = search.getBoundingClientRect()
      const spaceBeforeBody = bodyRect.top - mainRect.top + main.scrollTop
      const spaceAfterBody = searchRect.bottom - bodyRect.bottom
      const bottomPadding = Number.parseFloat(getComputedStyle(content).paddingBottom) || 0
      const available = Math.max(
        192,
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
            <Popover.Root>
              <Popover.Trigger asChild>
                <Button type="button" variant="outline" size="sm" aria-label="选择首页测试词作">
                  选词 <ChevronDown className="size-3.5" aria-hidden="true" />
                </Button>
              </Popover.Trigger>
              <Popover.Portal>
                <Popover.Content
                  align="end"
                  sideOffset={8}
                  className="z-50 w-52 rounded-md border border-border bg-popover p-1.5 text-popover-foreground shadow-md outline-none"
                >
                  <p className="px-2 py-1 text-xs text-muted-foreground">首页排版测试</p>
                  {PREVIEW_POEMS.map((candidate) => (
                    <Popover.Close asChild key={candidate.id}>
                      <button
                        type="button"
                        aria-current={candidate.id === previewPoemId ? 'true' : undefined}
                        onClick={() => onPreviewPoemChange(candidate.id)}
                        className={
                          'flex w-full items-center justify-between rounded-sm px-2 py-2 text-left text-sm transition-colors hover:bg-accent focus-visible:bg-accent focus-visible:outline-none ' +
                          (candidate.id === previewPoemId ? 'bg-accent font-medium' : '')
                        }
                      >
                        <span>{candidate.label}</span>
                        <span className="text-xs text-muted-foreground">{candidate.author}</span>
                      </button>
                    </Popover.Close>
                  ))}
                </Popover.Content>
              </Popover.Portal>
            </Popover.Root>
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
            <div ref={searchRef} className="w-full">
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
