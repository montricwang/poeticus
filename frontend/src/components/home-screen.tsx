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
  return (
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-background text-foreground">
      <header className="shrink-0 border-b border-border/50">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-5 py-4 md:px-8">
          <span className="text-lg font-semibold tracking-tight">Poeticus</span>
          <div className="flex items-center gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={onEnterReader}>
              阅读室 <ArrowRight className="size-4" aria-hidden="true" />
            </Button>
            <ThemeSwitcher />
          </div>
        </div>
      </header>
      <main
        id="home"
        className="poeticus-scrollport min-h-0 flex-1 overflow-y-auto overscroll-contain"
      >
        <div className="mx-auto w-full max-w-6xl px-5 md:px-8 lg:flex lg:min-h-full lg:flex-col lg:justify-center lg:pt-10 lg:pb-[6.5rem]">
          {/* 底部比顶部多留一个导航栏的高度：整体以视口为中心，长内容也不会被位移裁切。 */}
          <div className="lg:flex lg:flex-col lg:gap-10">
            <DailyRecommendation
              poem={featured}
              loading={featuredLoading}
              error={featuredError}
              disabled={selectionBlocked}
              onRead={onSelect}
            />
            <HorizontalEditorialDivider className="mx-auto my-10 w-full max-w-2xl lg:my-0" />
            <div className="w-full">
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
