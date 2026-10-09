import { useEffect, useState, type Dispatch, type SetStateAction } from 'react'

import { fetchPoemPage } from '@/data/poem-library'
import type { PoemFilters, PoemPage } from '@/data/poem-library'

const PAGE_SIZE = 20

export function usePoemCatalog(setPoemId: Dispatch<SetStateAction<string | null>>) {
  const [catalog, setCatalog] = useState<PoemPage | null>(null)
  const [filters, setFilters] = useState<PoemFilters>({
    limit: PAGE_SIZE,
    offset: 0,
  })
  const [searchInput, setSearchInput] = useState('')
  const [catalogLoading, setCatalogLoading] = useState(true)
  const [catalogError, setCatalogError] = useState('')

  // 目录轻量分页，不携带完整正文。
  useEffect(() => {
    const controller = new AbortController()
    void fetchPoemPage(filters, controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return
        setCatalog(page)
        setPoemId((current) => current ?? page.items[0]?.id ?? null)
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setCatalogError(error instanceof Error ? error.message : '无法获取目录')
      })
      .finally(() => {
        if (!controller.signal.aborted) setCatalogLoading(false)
      })
    return () => controller.abort()
  }, [filters, setPoemId])

  function updateCatalogFilters(next: PoemFilters) {
    // 上一页目录在请求期间继续存在，避免空列表导致侧栏重排。
    setCatalogLoading(true)
    setCatalogError('')
    setFilters(next)
  }

  return {
    catalog,
    filters,
    searchInput,
    setSearchInput,
    catalogLoading,
    catalogError,
    updateCatalogFilters,
  }
}
