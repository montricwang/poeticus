import { useEffect, useState } from 'react'

import { fetchPoem } from '@/data/poem-library'
import type { Poem } from '@/data/poem-library'

// 首页排版调试用的真实作品；词牌与作品 ID 只在这里维护。
export const PREVIEW_POEMS = [
  { label: '杨柳枝', author: '温庭筠', id: '378a4549-c42a-4aa9-9011-aead9ac95fd6' },
  { label: '菩萨蛮', author: '温庭筠', id: 'd051e331-50a7-4349-8d19-a0a68a2d8c90' },
  { label: '水调歌头', author: '苏轼', id: '38ed0c71-f117-4efd-b19e-bee072f6f103' },
  { label: '如梦令', author: '柳永', id: 'b182c939-9941-43a5-9d5d-822b9413d177' },
  { label: '戚氏', author: '柳永', id: 'e1fe9c90-c29b-468a-910d-973a331da960' },
  { label: '八声甘州', author: '柳永', id: 'ab54cb83-64d4-454f-83c8-857f146e6505' },
  { label: '满庭芳', author: '苏轼', id: '6414f92e-2d36-4294-abe2-e71d027fd7ba' },
  { label: '兰陵王', author: '周邦彦', id: '0bcfe60f-6708-4617-a79f-88fd94e905ac' },
  { label: '踏莎行', author: '晏殊', id: '95cd6469-a450-49d7-b1d8-2cbc64108646' },
] as const

export function useFeaturedPoem() {
  const [previewPoemId, setCurrentPreviewPoemId] = useState<string>(PREVIEW_POEMS[4].id)
  const [featured, setFeatured] = useState<Poem | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    void fetchPoem(previewPoemId, controller.signal)
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
  }, [previewPoemId])

  function selectPreviewPoem(id: string) {
    if (id === previewPoemId) return
    setFeatured(null)
    setLoading(true)
    setError('')
    setCurrentPreviewPoemId(id)
  }

  return { featured, loading, error, previewPoemId, setPreviewPoemId: selectPreviewPoem }
}
