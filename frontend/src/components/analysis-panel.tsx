import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react'
import { LoaderCircle } from 'lucide-react'

import { AnalysisReveal, AnalysisTextEntrance } from '@/components/analysis-text-entrance'
import { HorizontalEditorialDivider } from '@/components/editorial-divider'
import { Button } from '@/components/ui/button'
import { useScrollActivity } from '@/hooks/use-scroll-activity'
import { cn } from '@/lib/utils'
import type { PoemAnalysis } from '@/types/poem'

type AnalysisPanelProps = {
  analysis: PoemAnalysis | null
  analyzing: boolean
  error: string
  limitNotice: boolean
  onAnalyze: () => void
  switching: boolean
  animateResult: boolean
  onAnimationStarted: () => void
  scrollTopRef: RefObject<number>
  fillAvailableHeight?: boolean
  className?: string
}

type AnalysisResultProps = {
  analysis: PoemAnalysis
  animateResult: boolean
  onAnimationStarted: () => void
}

function AnalysisResult({ analysis, animateResult, onAnimationStarted }: AnalysisResultProps) {
  // 结果节点只在赏析真正返回后挂载；在这里把本次是否需要动画固定下来，
  // 这样父层登记“已经播过”后，不会中途把正在播放的逐字动画取消。
  const [animate] = useState(animateResult)

  useEffect(() => {
    if (animate) onAnimationStarted()
  }, [animate, onAnimationStarted])

  return (
    <div className={cn('space-y-6', animate && 'poeticus-analysis-result-enter')}>
      <AnalysisReveal animate={animate}>
        {(revealed) => (
          <section>
            <AnalysisTextEntrance
              as="h3"
              text="现代汉语译文"
              animate={animate && revealed}
              className="mb-3 text-base font-semibold"
            />
            <AnalysisTextEntrance
              as="p"
              text={analysis.translation}
              animate={animate && revealed}
              className="whitespace-pre-wrap text-sm leading-7 text-foreground/85"
            />
          </section>
        )}
      </AnalysisReveal>

      <HorizontalEditorialDivider className="w-10" />

      <section>
        <AnalysisReveal animate={animate}>
          {(revealed) => (
            <AnalysisTextEntrance
              as="h3"
              text="词语注释"
              animate={animate && revealed}
              className="mb-4 text-base font-semibold"
            />
          )}
        </AnalysisReveal>

        {analysis.glosses.length === 0 ? (
          <AnalysisReveal animate={animate}>
            {() => (
              <p className="text-sm text-muted-foreground">本次赏析没有需要单独解释的词语。</p>
            )}
          </AnalysisReveal>
        ) : (
          <div className="space-y-3">
            {analysis.glosses.map((gloss, index) => (
              <AnalysisReveal key={index} animate={animate}>
                {(revealed) => (
                  <div>
                    <AnalysisTextEntrance
                      as="h4"
                      text={gloss.term}
                      animate={animate && revealed}
                      className="mb-1 font-serif text-sm font-semibold"
                    />
                    <AnalysisTextEntrance
                      as="p"
                      text={gloss.explanation}
                      animate={animate && revealed}
                      className="text-sm leading-7 text-muted-foreground"
                    />
                  </div>
                )}
              </AnalysisReveal>
            ))}
          </div>
        )}
      </section>

      <HorizontalEditorialDivider className="w-10" />

      <AnalysisReveal animate={animate}>
        {(revealed) => (
          <section>
            <AnalysisTextEntrance
              as="h3"
              text="文学赏析"
              animate={animate && revealed}
              className="mb-3 text-base font-semibold"
            />
            <AnalysisTextEntrance
              as="p"
              text={analysis.commentary}
              animate={animate && revealed}
              className="whitespace-pre-wrap text-sm leading-7 text-foreground/85"
            />
          </section>
        )}
      </AnalysisReveal>
    </div>
  )
}

export function AnalysisPanel({
  analysis,
  analyzing,
  error,
  limitNotice,
  onAnalyze,
  switching,
  animateResult,
  onAnimationStarted,
  scrollTopRef,
  fillAvailableHeight = false,
  className,
}: AnalysisPanelProps) {
  const scrollportRef = useRef<HTMLDivElement>(null)
  const markScrollActivity = useScrollActivity()
  const [hasContentAbove, setHasContentAbove] = useState(false)
  const [hasContentBelow, setHasContentBelow] = useState(false)

  const updateScrollEdges = useCallback((element: HTMLDivElement) => {
    const remaining = element.scrollHeight - element.clientHeight - element.scrollTop
    setHasContentAbove(element.scrollTop > 8)
    setHasContentBelow(remaining > 8)
  }, [])

  // The content can grow after its first paint; update fade edges as it resizes.
  useEffect(() => {
    const element = scrollportRef.current
    if (!element) return
    const observer = new ResizeObserver(() => updateScrollEdges(element))
    observer.observe(element)
    const content = element.firstElementChild
    if (content) observer.observe(content)
    const frame = window.requestAnimationFrame(() => updateScrollEdges(element))
    return () => {
      window.cancelAnimationFrame(frame)
      observer.disconnect()
    }
  }, [analysis, analyzing, error, fillAvailableHeight, updateScrollEdges])

  // 对话/赏析相互切换会卸载当前面板，恢复先前的实际滚动位置。
  // 用 layout effect 在浏览器绘制前复位，避免先跳到顶部再闪回原处。
  useLayoutEffect(() => {
    const scrollport = scrollportRef.current
    if (!scrollport) return
    scrollport.scrollTop = scrollTopRef.current
    return () => {
      scrollTopRef.current = scrollport.scrollTop
    }
  }, [scrollTopRef])

  return (
    <section
      aria-label="整首赏析"
      className={cn(
        'flex min-h-0 min-w-0 flex-col bg-transparent',
        fillAvailableHeight
          ? 'flex-1'
          : analysis
            ? 'h-auto max-h-[var(--companion-panel-max-height)]'
            : 'h-auto',
        className,
      )}
    >
      <div
        ref={scrollportRef}
        onScroll={(event) => {
          const element = event.currentTarget
          scrollTopRef.current = element.scrollTop
          updateScrollEdges(element)
        }}
        onWheel={(event) => markScrollActivity(event.currentTarget)}
        onTouchMove={(event) => markScrollActivity(event.currentTarget)}
        className={cn(
          'poeticus-scrollport poeticus-auto-scrollbar min-h-0',
          fillAvailableHeight
            ? 'flex-1 overflow-y-auto py-4 pr-2'
            : analysis
              ? 'overflow-y-auto py-4 pr-2'
              : 'py-2 pr-2',
          hasContentAbove && 'poeticus-scroll-fade-top',
          hasContentBelow && 'poeticus-scroll-fade-bottom',
        )}
      >
        {analyzing ? (
          <div
            role="status"
            className={cn(
              'flex flex-col items-center justify-center gap-4 text-center',
              fillAvailableHeight ? 'h-full' : 'py-8',
            )}
          >
            <LoaderCircle className="size-6 animate-spin text-muted-foreground" />
            <p className="text-sm text-muted-foreground">正在生成译文、注释和文学赏析……</p>
          </div>
        ) : error ? (
          <div
            role={limitNotice ? 'status' : 'alert'}
            className={cn(
              'mx-auto max-w-md rounded-xl p-4',
              limitNotice ? 'bg-muted/30 text-foreground' : 'bg-destructive/10 text-destructive',
            )}
          >
            <h3 className="font-medium">{limitNotice ? '稍等一会儿' : '赏析失败'}</h3>
            <p className="mt-2 text-sm leading-7">{error}</p>
            {!limitNotice && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="mt-4"
                onClick={onAnalyze}
                disabled={switching}
              >
                重新生成
              </Button>
            )}
          </div>
        ) : analysis ? (
          <AnalysisResult
            analysis={analysis}
            animateResult={animateResult}
            onAnimationStarted={onAnimationStarted}
          />
        ) : (
          <div
            className={cn(
              'flex items-center justify-center text-center',
              fillAvailableHeight ? 'h-full' : 'py-8',
            )}
          >
            <div className="space-y-3">
              <p className="text-sm leading-7 text-muted-foreground">
                生成译文、词语注释与文学赏析。
              </p>
              <Button type="button" onClick={onAnalyze} disabled={switching}>
                生成整首赏析
              </Button>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
