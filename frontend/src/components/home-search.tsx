import type { FormEvent } from 'react'
import { ArrowLeft, ArrowRight, Search, X } from 'lucide-react'

import { HorizontalEditorialDivider } from '@/components/editorial-divider'
import { Button } from '@/components/ui/button'
import { poemIncipit, poemLabel } from '@/data/poem-library'
import type { PoemFilters, PoemPage } from '@/data/poem-library'

type HomeSearchProps = {
  catalog: PoemPage | null
  filters: PoemFilters
  query: string
  loading: boolean
  error: string
  disabled: boolean
  onQueryChange: (value: string) => void
  onFiltersChange: (filters: PoemFilters) => void
  onSelect: (id: string) => void
}

/** 首页检索入口与搜索结果；使用已有馆藏分页接口。 */
export function HomeSearch({
  catalog,
  filters,
  query,
  loading,
  error,
  disabled,
  onQueryChange,
  onFiltersChange,
  onSelect,
}: HomeSearchProps) {
  const hasSearch = !!filters.q?.trim()
  const page = catalog ? Math.floor(catalog.offset / filters.limit) + 1 : 1
  const pageCount = catalog ? Math.ceil(catalog.total / filters.limit) : 0

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    // 手机提交时先收起软键盘，由首页切换布局；不滚动到结果框二次跳动。
    event.currentTarget.querySelector('input')?.blur()
    onFiltersChange({ q: query.trim(), limit: 20, offset: 0 })
  }

  function clearSearch() {
    onQueryChange('')
    onFiltersChange({ limit: 20, offset: 0 })
  }

  return (
    <>
      <section aria-label="馆藏搜索" className="mx-auto w-full max-w-2xl">
        <h1 className="mb-5 text-center font-serif text-xl font-medium tracking-[0.12em] sm:text-2xl">
          美要眇兮宜修
        </h1>
        <form
          role="search"
          onSubmit={submitSearch}
          autoComplete="off"
          className="peer flex min-h-15 items-center gap-3 bg-transparent px-4 sm:min-h-17 sm:px-5"
        >
          <Search className="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
          <input
            type="search"
            name="q"
            autoComplete="off"
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
        <HorizontalEditorialDivider className="w-full peer-focus-within:bg-ring" />
      </section>

      {hasSearch && (
        <section
          aria-label="搜索结果"
          className="mx-auto mt-10 w-full max-w-4xl scroll-mt-6 px-5 pb-20 md:px-8 lg:mt-12"
        >
          <div className="mb-5 flex items-baseline justify-between gap-4 border-b border-border/70 pb-4">
            <div>
              <h2 className="font-serif text-xl">搜索结果</h2>
              <p className="mt-1 text-xs text-muted-foreground" role="status">
                {loading ? '正在搜索……' : error ? '搜索失败' : `找到 ${catalog?.total ?? 0} 首作品`}
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
                    disabled={disabled}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="poeticus-catalog-title block truncate font-medium">
                        {poemLabel(work)}
                      </span>
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
    </>
  )
}
