import { useEffect, useState } from 'react'

import { fetchPoem } from '@/data/poem-library'
import type { Poem } from '@/data/poem-library'

// 临时固定推荐词作；正式推荐策略留待后续功能实现。
const FEATURED_POEM_ID = 'e1fe9c90-c29b-468a-910d-973a331da960'

export function useFeaturedPoem() {
  const [featured, setFeatured] = useState<Poem | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    void fetchPoem(FEATURED_POEM_ID, controller.signal)
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
