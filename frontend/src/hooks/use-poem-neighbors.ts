import { useEffect, useState } from 'react'

import { fetchPoemNeighbors } from '@/data/poem-library'
import type { PoemNeighbors } from '@/data/poem-library'

export function usePoemNeighbors(poemId: string | null): PoemNeighbors | null {
  const [result, setResult] = useState<{ poemId: string; neighbors: PoemNeighbors } | null>(null)

  useEffect(() => {
    if (!poemId) return
    const controller = new AbortController()
    void fetchPoemNeighbors(poemId, controller.signal)
      .then((neighbors) => {
        if (!controller.signal.aborted) setResult({ poemId, neighbors })
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setResult({ poemId, neighbors: { previous_id: null, next_id: null } })
        }
      })
    return () => controller.abort()
  }, [poemId])

  // 上一首的响应即便晚于下一首，也不能用来决定当前作品的边界。
  return result?.poemId === poemId ? result.neighbors : null
}
