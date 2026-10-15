import { useEffect, useState } from 'react'

import { fetchPoem, fetchPoemPage } from '@/data/poem-library'
import type { Poem } from '@/data/poem-library'

/** One random work per page visit. Keep it when switching between Home and Reader. */
export function useFeaturedPoem() {
  const [featured, setFeatured] = useState<Poem | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      try {
        const { total } = await fetchPoemPage({ offset: 0, limit: 1 }, controller.signal)
        if (total === 0) throw new Error('馆藏中暂时没有可推荐的作品')
        // The paginated catalog is ordered; choosing its offset gives every work a chance.
        const offset = Math.floor(Math.random() * total)
        const page = await fetchPoemPage({ offset, limit: 1 }, controller.signal)
        const candidate = page.items[0]
        if (!candidate) throw new Error('未找到推荐作品')
        const poem = await fetchPoem(candidate.id, controller.signal)
        if (!poem.body_segments.some((segment) => segment.trim())) {
          throw new Error('这首作品还没有可阅读的正文')
        }
        if (!controller.signal.aborted) setFeatured(poem)
      } catch (cause: unknown) {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : '暂时无法加载推荐作品')
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    void load()
    return () => controller.abort()
  }, [])

  return { featured, loading, error }
}
