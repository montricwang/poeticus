import { useEffect, useRef } from 'react'
import { ChevronLeft, ChevronRight, ChevronUp, Search, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { HorizontalEditorialDivider } from '@/components/editorial-divider'
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
  embedded?: boolean
}

/** 展示分页目录和筛选框；窄屏抽屉打开时约束键盘焦点。 */
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
  embedded = false,
}: PoemCatalogProps) {
  const panelRef = useRef<HTMLElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return

    /** Esc 关闭目录，窄屏时 Tab 焦点限制在打开的抽屉内。 */
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

  // 桌面单行书目固定为 56px。按列表可用高度翻页，保留原浏览位置附近的作品。
  useEffect(() => {
    if (!embedded || !open) return
    const list = listRef.current
    if (!list) return

    const resize = () => {
      const limit = Math.max(1, Math.floor(list.clientHeight / 56))
      if (limit === filters.limit) return
      onFiltersChange({
        ...filters,
        limit,
        offset: Math.floor(filters.offset / limit) * limit,
      })
    }

    resize()
    const observer = new ResizeObserver(resize)
    observer.observe(list)
    return () => observer.disconnect()
  }, [embedded, open, filters, onFiltersChange])

  const hasQuery = !!filters.q?.trim()
  const page = catalog ? Math.floor(catalog.offset / filters.limit) + 1 : 1

  return (
    <aside
      id="poem-catalog"
      ref={panelRef}
      aria-label="作品目录"
      className={
        'flex h-full min-h-0 flex-col ' +
        (embedded
          ? 'w-full border-0 bg-transparent'
          : 'w-screen border-r border-border bg-background sm:w-[min(88vw,420px)]')
      }
    >
      <div
        className={
          'flex items-center justify-between px-4 py-3 ' +
          (embedded ? '' : 'border-b border-border/60')
        }
      >
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
          {embedded ? (
            <ChevronUp className="size-4" aria-hidden="true" />
          ) : (
            <X className="size-4" aria-hidden="true" />
          )}
        </Button>
      </div>

      <form
        className={embedded ? 'px-3 pt-3' : 'border-b border-border/50 p-3'}
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
      </form>

      {embedded && (
        <div className="flex h-[clamp(1rem,3vh,2.5rem)] shrink-0 items-center justify-center">
          <HorizontalEditorialDivider className="w-full max-w-130" />
        </div>
      )}

      <div
        ref={listRef}
        className={
          'poeticus-scrollport min-h-0 flex-1 overscroll-contain ' +
          (embedded ? 'overflow-hidden' : 'overflow-y-auto')
        }
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
            {(catalog?.items ?? []).map((work) => {
              const entry = (
                <button
                  type="button"
                  disabled={selectionBlocked}
                  aria-current={work.id === activePoemId ? 'true' : undefined}
                  onClick={() => onSelect(work.id)}
                  className={
                    'w-full border-l-2 border-transparent px-4 text-left transition-colors hover:bg-muted/50 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-60 ' +
                    (embedded ? 'flex h-14 items-center gap-3 ' : 'block py-3 ') +
                    (work.id === activePoemId ? 'border-l-foreground/70 bg-muted/40 ' : '')
                  }
                >
                  {embedded ? (
                    <>
                      <span
                        className="poeticus-catalog-title max-w-[62%] shrink-0 truncate text-base font-medium text-foreground"
                        title={embedded ? undefined : poemLabel(work)}
                      >
                        {poemLabel(work)}
                      </span>
                      <span
                        className="min-w-0 flex-1 truncate font-serif text-sm text-muted-foreground"
                        title={embedded ? undefined : work.incipit}
                      >
                        {poemIncipit(work)}
                      </span>
                      <span
                        className="max-w-20 shrink-0 truncate text-xs text-muted-foreground"
                        title={embedded ? undefined : (work.author ?? '作者未核实')}
                      >
                        {work.author ?? '佚名'}
                      </span>
                    </>
                  ) : (
                    <>
                      <div className="flex min-w-0 items-baseline gap-2">
                        <span
                          className="min-w-0 flex-1 truncate text-sm font-medium text-foreground"
                          title={embedded ? undefined : poemLabel(work)}
                        >
                          {poemLabel(work)}
                        </span>
                        <span
                          className="max-w-20 shrink-0 truncate text-xs text-muted-foreground"
                          title={embedded ? undefined : (work.author ?? '作者未核实')}
                        >
                          {work.author ?? '佚名'}
                        </span>
                      </div>
                      <span
                        className="mt-1.5 block truncate font-serif text-sm text-muted-foreground"
                        title={embedded ? undefined : work.incipit}
                      >
                        {poemIncipit(work)}
                      </span>
                    </>
                  )}
                </button>
              )
              return (
                <li
                  key={work.id}
                  className={embedded ? '' : 'border-b border-border/40 last:border-0'}
                >
                  {entry}
                </li>
              )
            })}
          </ul>
        )}
      </div>

      <div
        className={
          embedded
            ? 'shrink-0'
            : 'flex items-center justify-between gap-2 border-t border-border/60 px-3 py-2'
        }
      >
        {embedded && <HorizontalEditorialDivider className="mx-auto mb-3 w-full max-w-130" />}
        <div
          className={
            embedded
              ? 'mx-auto flex w-full max-w-130 items-center justify-between gap-2'
              : 'contents'
          }
        >
          <span className="mr-auto text-xs text-muted-foreground lg:order-2 lg:mr-0 lg:text-sm">
            {catalog
              ? embedded
                ? `第 ${page} / ${Math.max(1, Math.ceil(catalog.total / filters.limit))} 页`
                : `第 ${page} 页`
              : '—'}
            {loading ? ' · 加载中' : ''}
          </span>
          <Button
            className="lg:order-1"
            type="button"
            variant="ghost"
            size={embedded ? 'sm' : 'icon-sm'}
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
            {embedded && '上一页'}
          </Button>
          <Button
            className="lg:order-3"
            type="button"
            variant="ghost"
            size={embedded ? 'sm' : 'icon-sm'}
            aria-label="下一页"
            disabled={loading || !catalog || filters.offset + filters.limit >= catalog.total}
            onClick={() =>
              onFiltersChange({
                ...filters,
                offset: filters.offset + filters.limit,
              })
            }
          >
            {embedded && '下一页'}
            <ChevronRight className="size-4" aria-hidden="true" />
          </Button>
        </div>
      </div>
    </aside>
  )
}
