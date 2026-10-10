import { useEffect, useRef } from 'react'
import { ChevronLeft, ChevronRight, Search, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { poemIncipit, poemLabel } from '@/data/poem-library'
import type { PoemFilters, PoemPage } from '@/data/poem-library'
import { OVERLAY_CATALOG_MEDIA } from '@/lib/responsive-layout'

type PoemCatalogProps = {
  catalog: PoemPage | null
  filters: PoemFilters
  query: string
  loading: boolean
  error: string
  activePoemId: string | null
  selectionBlocked: boolean
  onQueryChange: (value: string) => void
  onFiltersChange: (filters: PoemFilters) => void
  onSelect: (id: string) => void
  onClose: () => void
  open: boolean
}

export function PoemCatalog({
  catalog,
  filters,
  query,
  loading,
  error,
  activePoemId,
  selectionBlocked,
  onQueryChange,
  onFiltersChange,
  onSelect,
  onClose,
  open,
}: PoemCatalogProps) {
  const panelRef = useRef<HTMLElement>(null)

  useEffect(() => {
    if (!open) return

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose()
      }
      if (event.key !== 'Tab' || !window.matchMedia(OVERLAY_CATALOG_MEDIA).matches) {
        return
      }
      const elements = panelRef.current?.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input:not(:disabled), a[href], [tabindex="0"]',
      )
      if (!elements?.length) return
      const first = elements[0]
      const last = elements[elements.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose, open])

  const hasQuery = !!filters.q?.trim()
  const page = catalog ? Math.floor(catalog.offset / filters.limit) + 1 : 1

  return (
    <aside
      id="poem-catalog"
      ref={panelRef}
      aria-label="作品目录"
      className="flex h-full min-h-0 w-screen flex-col sm:w-[min(88vw,420px)] border-r border-border bg-background 2xl:sticky 2xl:top-5 2xl:h-[calc(100vh-7rem)] 2xl:max-h-[900px] 2xl:w-full 2xl:border-0 2xl:bg-transparent"
    >
      <div className="flex items-center justify-between border-b border-border/60 px-4 py-3">
        <div className="flex min-w-0 items-baseline gap-2">
          <h2 className="font-medium">作品目录</h2>
          <span className="text-xs text-muted-foreground" aria-live="polite">
            {catalog ? `${catalog.total} 首` : '加载中'}
          </span>
        </div>
        <Button
          type="button"
          size="icon-sm"
          variant="ghost"
          aria-label="收起作品目录"
          onClick={onClose}
        >
          <X className="size-4 2xl:hidden" aria-hidden="true" />
          <ChevronLeft className="hidden size-4 2xl:block" aria-hidden="true" />
        </Button>
      </div>

      <form
        className="border-b border-border/50 p-3"
        role="search"
        onSubmit={(event) => {
          event.preventDefault()
          onFiltersChange({ limit: filters.limit, offset: 0, q: query.trim() })
        }}
      >
        <div className="flex items-center gap-2 rounded-md border border-border bg-background px-2.5 focus-within:ring-2 focus-within:ring-ring/30">
          <Search className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <input
            aria-label="搜索作者、词牌、词题、正文"
            className="h-10 w-full min-w-0 bg-transparent text-base outline-none placeholder:text-muted-foreground"
            placeholder="作者、词牌、词题或诗句"
            maxLength={100}
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
          />
          <Button type="submit" size="xs" variant="ghost" disabled={loading}>
            查找
          </Button>
        </div>
        <p className="mt-2 px-1 text-xs text-muted-foreground">空格分隔多个词，全部匹配即可</p>
      </form>

      <div
        className="poeticus-scrollport min-h-0 flex-1 overflow-y-auto overscroll-contain"
        aria-busy={loading}
      >
        {error ? (
          <div role="alert" className="space-y-3 p-4 text-sm text-destructive">
            <p>目录获取失败：{error}</p>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => onFiltersChange({ ...filters })}
            >
              重试
            </Button>
          </div>
        ) : loading && !catalog ? (
          <p className="p-4 text-sm text-muted-foreground" role="status">
            正在查找作品……
          </p>
        ) : catalog && catalog.total === 0 ? (
          <p className="p-4 text-sm leading-6 text-muted-foreground">
            没有找到匹配作品。试试减少搜索词。
          </p>
        ) : (
          <ul aria-label={hasQuery ? '搜索结果' : '作品列表'}>
            {(catalog?.items ?? []).map((work) => (
              <li key={work.id} className="border-b border-border/40 last:border-0">
                <button
                  type="button"
                  disabled={selectionBlocked}
                  aria-current={work.id === activePoemId ? 'true' : undefined}
                  onClick={() => onSelect(work.id)}
                  className={
                    'block w-full border-l-2 border-transparent px-4 py-3 text-left transition-colors hover:bg-muted/50 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-60 ' +
                    (work.id === activePoemId ? 'border-l-foreground/70 bg-muted/40 ' : '')
                  }
                >
                  <div className="flex min-w-0 items-baseline gap-2">
                    <span
                      className="min-w-0 flex-1 truncate text-sm font-medium text-foreground"
                      title={poemLabel(work)}
                    >
                      {poemLabel(work)}
                    </span>
                    <span
                      className="max-w-20 shrink-0 truncate text-xs text-muted-foreground"
                      title={work.author ?? '作者未核实'}
                    >
                      {work.author ?? '佚名'}
                    </span>
                  </div>
                  <span
                    className="mt-1.5 block truncate font-serif text-sm text-muted-foreground"
                    title={work.incipit}
                  >
                    {poemIncipit(work)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex items-center justify-between gap-2 border-t border-border/60 px-3 py-2">
        <span className="text-xs text-muted-foreground">
          {catalog ? `第 ${page} 页` : '—'}
          {loading ? ' · 加载中' : ''}
        </span>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="上一页"
            disabled={loading || filters.offset === 0}
            onClick={() =>
              onFiltersChange({
                ...filters,
                offset: Math.max(0, filters.offset - filters.limit),
              })
            }
          >
            <ChevronLeft className="size-4" aria-hidden="true" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="下一页"
            disabled={loading || !catalog || filters.offset + filters.limit >= catalog.total}
            onClick={() =>
              onFiltersChange({
                ...filters,
                offset: filters.offset + filters.limit,
              })
            }
          >
            <ChevronRight className="size-4" aria-hidden="true" />
          </Button>
        </div>
      </div>
    </aside>
  )
}
