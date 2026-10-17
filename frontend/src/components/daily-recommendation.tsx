import { useEffect, useLayoutEffect, useRef, useState } from 'react'

import type { Poem } from '@/data/poem-library'
import { FeaturedPoemDisplay } from '@/components/featured-poem-display'
import { ReadPoemSeal } from '@/components/read-poem-seal'

type DailyRecommendationProps = {
  poem: Poem | null
  loading: boolean
  error: string
  disabled: boolean
  onRead: (id: string) => void
}

/** 首页根据视口宽度选用唯一排版，并组合「诗文／印章」，不影响阅读室。 */
export function DailyRecommendation({
  poem,
  loading,
  error,
  disabled,
  onRead,
}: DailyRecommendationProps) {
  const [continuous, setContinuous] = useState(
    () => window.matchMedia('(max-width: 1023px)').matches,
  )

  const recommendationRef = useRef<HTMLDivElement>(null)
  const sealRef = useRef<HTMLDivElement>(null)
  const [mobileSealLeft, setMobileSealLeft] = useState(0)

  // 印章跟随实际诗文左缘，不参与正文的横向居中。
  useLayoutEffect(() => {
    if (!poem || !continuous) return
    const area = recommendationRef.current
    const seal = sealRef.current
    const article = area?.querySelector<HTMLElement>('.home-featured-poem')
    if (!area || !seal || !article) return

    const place = () => {
      const left = article.getBoundingClientRect().left - area.getBoundingClientRect().left
      const next = Math.max(0, Math.round(left - seal.offsetWidth - 12))
      setMobileSealLeft((previous) => (previous === next ? previous : next))
    }

    place()
    const observer = new ResizeObserver(place)
    observer.observe(area)
    observer.observe(article)
    void document.fonts.ready.then(() => {
      if (area.isConnected) place()
    })
    return () => observer.disconnect()
  }, [poem, continuous])

  // 首页只保留一套适合当前设备的排版；窗口跨越断点时同步切换。
  useEffect(() => {
    const media = window.matchMedia('(max-width: 1023px)')
    const update = () => setContinuous(media.matches)
    media.addEventListener('change', update)
    update()
    return () => media.removeEventListener('change', update)
  }, [])

  return (
    <section aria-label="推荐作品" className="relative">
      {poem ? (
        // 手机端仅在左侧为印章预留 40px，正文向右偏移 20px，使印章＋正文整体居中。
        <div
          ref={recommendationRef}
          className="relative mx-auto grid w-full max-w-2xl grid-cols-[2.5rem_minmax(0,1fr)] items-end lg:grid-cols-[4rem_minmax(0,1fr)_4rem]"
        >
          <div
            ref={sealRef}
            className="absolute bottom-0 z-10 flex shrink-0 lg:static lg:justify-end lg:pr-3"
            style={{ left: mobileSealLeft }}
          >
            <ReadPoemSeal disabled={disabled} onClick={() => onRead(poem.id)} />
          </div>
          <div className="col-start-2 min-w-0">
            <FeaturedPoemDisplay poem={poem} continuous={continuous} />
          </div>
          <div aria-hidden="true" className="hidden lg:col-start-3 lg:block" />
        </div>
      ) : (
        <p role="status" className="py-20 text-center text-sm text-muted-foreground">
          {loading ? '正在寻一首词……' : error || '暂时没有推荐作品'}
        </p>
      )}
    </section>
  )
}
