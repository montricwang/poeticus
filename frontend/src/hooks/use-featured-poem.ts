import { useEffect, useState } from 'react'

import { fetchPoem } from '@/data/poem-library'
import type { Poem } from '@/data/poem-library'

// 调试首页竖排时固定为辛弃疾《破阵子·为陈同甫赋壮词以寄之》；之后再确定每日推荐规则。
const PREVIEW_POEM_ID = '2098ddf7-55bb-4923-be66-6af4cae58d78'

export function useFeaturedPoem() {
  const [featured, setFeatured] = useState<Poem | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    void fetchPoem(PREVIEW_POEM_ID, controller.signal)
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
