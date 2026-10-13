import { useState, type RefObject } from 'react'

import { poemContext, poemText } from '@/data/poem-library'
import type { Poem } from '@/data/poem-library'
import type { PoemAnalysis } from '@/types/poem'
import { UsageLimitNotice } from '@/lib/chat-stream'

type AnalysisOptions = {
  poemId: string | null
  activePoem: Poem | null
  switchControllerRef: RefObject<AbortController | null>
}

/** 管理整首赏析请求和结果，仅在当前作品未切换时允许发起请求。 */
export function usePoemAnalysis({ poemId, activePoem, switchControllerRef }: AnalysisOptions) {
  const [analysis, setAnalysis] = useState<PoemAnalysis | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisError, setAnalysisError] = useState('')
  const [analysisLimitNotice, setAnalysisLimitNotice] = useState(false)
  const poem = activePoem ? poemText(activePoem) : ''

  /** 调用非流式赏析接口，并区分额度提示与其他失败。 */
  async function analyzePoem() {
    if (!activePoem || activePoem.id !== poemId || switchControllerRef.current) return
    setAnalyzing(true)
    setAnalysisError('')
    setAnalysisLimitNotice(false)

    try {
      const response = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          poem,
          context: poemContext(activePoem),
        }),
      })

      if (!response.ok) {
        const error = await response.json().catch(() => null)
        const message =
          typeof error?.detail === 'string' ? error.detail : `请求失败：HTTP ${response.status}`
        throw response.status === 429 ? new UsageLimitNotice(message) : new Error(message)
      }

      const result: PoemAnalysis = await response.json()
      setAnalysis(result)
    } catch (error) {
      setAnalysisError(error instanceof Error ? error.message : '赏析请求失败')
      setAnalysisLimitNotice(error instanceof UsageLimitNotice)
    } finally {
      setAnalyzing(false)
    }
  }

  function resetAnalysis() {
    setAnalysis(null)
    setAnalysisError('')
    setAnalysisLimitNotice(false)
  }

  return {
    analysis,
    analyzing,
    analysisError,
    analysisLimitNotice,
    analyzePoem,
    resetAnalysis,
  }
}
