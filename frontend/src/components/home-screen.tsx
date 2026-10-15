import { useEffect, useRef, type FormEvent } from 'react'
import { ArrowLeft, ArrowRight, Search, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { ThemeSwitcher } from '@/components/theme-switcher'
import { poemIncipit, poemTitle } from '@/data/poem-library'
import type { Poem, PoemFilters, PoemPage } from '@/data/poem-library'
import { featuredExcerpt } from '@/lib/featured-poem'

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
  const resultsRef = useRef<HTMLElement>(null)
  const hasSearch = !!filters.q?.trim()
  const excerpt = featured ? featuredExcerpt(featured) : null
  const page = catalog ? Math.floor(catalog.offset / filters.limit) + 1 : 1
  const pageCount = catalog ? Math.ceil(catalog.total / filters.limit) : 0

  function showResults() {
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    resultsRef.current?.scrollIntoView({
      block: 'start',
      behavior: reducedMotion ? 'instant' : 'smooth',
    })
  }

  useEffect(() => {
    if (hasSearch) showResults()
  }, [hasSearch])

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onFiltersChange({ q: query.trim(), limit: 20, offset: 0 })
    if (hasSearch) showResults()
  }

  function clearSearch() {
    onQueryChange('')
    onFiltersChange({ limit: 20, offset: 0 })
  }

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
        <div className="mx-auto flex min-h-[calc(100dvh-69px)] max-w-6xl flex-col px-5 md:px-8">
          <section
            aria-label="今日一词"
            className="flex min-h-0 flex-1 flex-col items-center justify-center pt-8 pb-6 sm:pt-10"
          >
            <p className="mb-7 text-xs tracking-[0.28em] text-muted-foreground">今日一词</p>
            {featured && excerpt ? (
              <>
                <button
                  type="button"
                  onClick={() => onSelect(featured.id)}
                  disabled={selectionBlocked}
                  aria-label={`阅读${poemTitle(featured)}`}
                  className="group flex max-w-full cursor-pointer justify-center rounded-sm px-3 py-3 text-left transition-opacity hover:opacity-70 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none"
                >
                  <span
                    lang="zh-CN"
                    className="home-featured-poem h-[min(43dvh,22rem)] max-w-[calc(100vw-3rem)] overflow-hidden whitespace-pre-line font-serif text-[clamp(1.22rem,2vw,1.55rem)] leading-1.9 tracking-[0.035em]"
                    style={{ writingMode: 'vertical-rl', textOrientation: 'mixed' }}
                  >
                    {excerpt.text}
                  </span>
                </button>
                <p className="mt-5 max-w-full text-center text-sm text-foreground/75">
                  {poemTitle(featured)} <span className="mx-2 text-muted-foreground/60">·</span>
                  {featured.author ?? '佚名'}
                  {excerpt.isExcerpt && (
                    <span className="ml-2 text-xs text-muted-foreground">节选</span>
                  )}
                </p>
                <button
                  type="button"
                  disabled={selectionBlocked}
                  onClick={() => onSelect(featured.id)}
                  className="mt-2 text-xs text-muted-foreground underline-offset-4 hover:underline focus-visible:underline disabled:opacity-50"
                >
                  读这首词 <ArrowRight className="inline size-3" aria-hidden="true" />
                </button>
              </>
            ) : (
              <div
                className="flex min-h-64 items-center justify-center text-sm text-muted-foreground"
                role="status"
              >
                {featuredLoading ? '正在寻一首词……' : featuredError || '暂时没有推荐作品'}
              </div>
            )}
          </section>

          <section
            aria-label="馆藏搜索"
            className="mx-auto w-full max-w-2xl shrink-0 pb-[clamp(3rem,9dvh,6rem)]"
          >
            <h1 className="mb-5 text-center font-serif text-xl font-medium tracking-[0.12em] sm:text-2xl">
              在诗词中寻一处相逢
            </h1>
            <form
              role="search"
              onSubmit={submitSearch}
              className="flex min-h-15 items-center gap-3 rounded-xl border border-border bg-background px-4 shadow-[0_5px_26px_-18px_rgba(0,0,0,0.28)] focus-within:border-foreground/35 focus-within:ring-2 focus-within:ring-ring/15 sm:min-h-17 sm:px-5"
            >
              <Search className="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
              <input
                type="search"
                name="q"
                value={query}
                onChange={(event) => onQueryChange(event.target.value)}
                aria-label="搜索词人、词牌或诗句"
                maxLength={100}
                placeholder="搜词人、词牌，或记得的一句词……"
                className="min-w-0 flex-1 bg-transparent text-base text-foreground outline-none placeholder:text-muted-foreground/75"
              />
              {query && (
                <button
                  type="button"
                  aria-label="清空输入"
                  onClick={() => onQueryChange('')}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X className="size-4" aria-hidden="true" />
                </button>
              )}
              <Button type="submit" size="sm" className="shrink-0 px-4">
                搜索
              </Button>
            </form>
            <p className="mt-3 text-center text-xs text-muted-foreground">
              从现有馆藏中搜索，不必知道完整的词题。
            </p>
          </section>
        </div>

        {hasSearch && (
          <section
            ref={resultsRef}
            aria-label="搜索结果"
            className="mx-auto max-w-4xl scroll-mt-6 px-5 pb-20 md:px-8"
          >
            <div className="mb-5 flex items-baseline justify-between gap-4 border-b border-border/70 pb-4">
              <div>
                <h2 className="font-serif text-xl">搜索结果</h2>
                <p className="mt-1 text-xs text-muted-foreground" role="status">
                  {loading
                    ? '正在搜索……'
                    : error
                      ? '搜索失败'
                      : `找到 ${catalog?.total ?? 0} 首作品`}
                </p>
              </div>
              <button
                type="button"
                className="text-sm text-muted-foreground hover:text-foreground"
                onClick={clearSearch}
              >
                清除搜索
              </button>
            </div>
            {error && (
              <p role="alert" className="py-10 text-sm text-destructive">
                {error}
              </p>
            )}
            {!loading && !error && catalog?.items.length === 0 && (
              <p className="py-12 text-center text-sm text-muted-foreground">
                馆藏中没有找到匹配的作品，试试更短的诗句或作者名字。
              </p>
            )}
            {!loading && !error && (
              <ul className="divide-y divide-border/50">
                {catalog?.items.map((work) => (
                  <li key={work.id}>
                    <button
                      type="button"
                      className="group flex w-full min-w-0 items-baseline justify-between gap-6 py-4 text-left hover:text-foreground/70 focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50"
                      onClick={() => onSelect(work.id)}
                      disabled={selectionBlocked}
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium">{poemTitle(work)}</span>
                        <span className="mt-1 block truncate font-serif text-sm text-muted-foreground">
                          {poemIncipit(work)}
                        </span>
                      </span>
                      <span className="shrink-0 text-sm text-muted-foreground">
                        {work.author ?? '佚名'}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {!loading && !error && pageCount > 1 && (
              <nav
                aria-label="搜索结果翻页"
                className="mt-8 flex items-center justify-center gap-6 text-sm"
              >
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() =>
                    onFiltersChange({
                      ...filters,
                      offset: Math.max(0, filters.offset - filters.limit),
                    })
                  }
                >
                  <ArrowLeft className="size-4" aria-hidden="true" /> 上一页
                </Button>
                <span className="text-muted-foreground">
                  {page} / {pageCount}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={page >= pageCount}
                  onClick={() =>
                    onFiltersChange({ ...filters, offset: filters.offset + filters.limit })
                  }
                >
                  下一页 <ArrowRight className="size-4" aria-hidden="true" />
                </Button>
              </nav>
            )}
          </section>
        )}
      </main>
    </div>
  )
}
