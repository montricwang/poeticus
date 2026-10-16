import { useEffect, useState } from 'react'

import { fetchDailyPoem } from '@/data/poem-library'
import type { Poem } from '@/data/poem-library'

export function useFeaturedPoem() {
  const [featured, setFeatured] = useState<Poem | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    void fetchDailyPoem(controller.signal)
      .then((poem) => {
        if (!controller.signal.aborted) setFeatured(poem)
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : '暂时无法加载推荐作品')
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [])

  return { featured, loading, error }
}
