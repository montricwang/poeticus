import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'

import { VerticalEditorialDivider } from '@/components/editorial-divider'

type DesktopCompanionStageProps = {
  children: ReactNode
  ready: boolean
}

/**
 * Center the companion against the reading stage using its current content height.
 * A temporary quote can move the toolbar upward; clearing it must restore the
 * centered position instead of reserving the tallest height ever observed.
 */
export function DesktopCompanionStage({ children, ready }: DesktopCompanionStageProps) {
  const contentRef = useRef<HTMLDivElement>(null)
  const [currentHeight, setCurrentHeight] = useState(0)
  const [animateLayout, setAnimateLayout] = useState(false)

  useLayoutEffect(() => {
    const content = contentRef.current
    if (!content) return

    const observer = new ResizeObserver(() => {
      const height = Math.ceil(content.getBoundingClientRect().height)
      setCurrentHeight((previous) => (previous === height ? previous : height))
    })
    observer.observe(content)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!ready) return

    // Let the restored poem and conversation settle before enabling movement.
    // Otherwise the loading placeholder would animate into the first real layout.
    const timer = window.setTimeout(() => setAnimateLayout(true), 100)
    return () => window.clearTimeout(timer)
  }, [ready])

  // The grid remains at least 60dvh tall. Once the content exceeds that height,
  // max() returns zero so the companion can grow normally without clipping.
  const verticalOffset = `max(0px, calc(var(--desktop-reading-stage-center-offset) - ${currentHeight / 2}px))`
  const motionClass = animateLayout
    ? 'transition-[margin-top] duration-[420ms] ease-[var(--motion-ease-settle)] motion-reduce:transition-none'
    : ''
  const dividerHeight = Math.max(176, currentHeight - 8)

  return (
    <div className="grid min-h-[var(--desktop-reading-stage-min-height)] min-w-0 grid-cols-[1.5px_minmax(0,1fr)] items-start gap-x-6">
      <div className={motionClass} style={{ marginTop: verticalOffset }}>
        <VerticalEditorialDivider
          className={
            'mt-1 ' +
            (animateLayout
              ? 'transition-[height] duration-[420ms] ease-[var(--motion-ease-settle)] motion-reduce:transition-none'
              : '')
          }
          style={{ height: dividerHeight }}
        />
      </div>
      <div className={'min-w-0 ' + motionClass} style={{ marginTop: verticalOffset }}>
        <div ref={contentRef}>{children}</div>
      </div>
    </div>
  )
}
