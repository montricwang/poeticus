import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react'

import { VerticalEditorialDivider } from '@/components/editorial-divider'
import { motionDurationMs } from '@/lib/motion'

type ReaderCompanionLayoutProps = {
  reader: ReactNode
  children: ReactNode
  ready: boolean
  idle: boolean
}

type CompanionGeometry = {
  stageHeight: number
  contentHeight: number
  toolbarHeight: number
}

/**
 * Owns the reader/companion boundary. The divider is a grid sibling, never
 * nested inside the companion content, so it cannot inherit its scroll clips,
 * opacity transitions or text layout. All three grid tracks share one parent.
 *
 * Only the companion's content is measured. Its position and the boundary
 * divider's position/height are derived from the same geometry.
 */
export function ReaderCompanionLayout({
  reader,
  children,
  ready,
  idle,
}: ReaderCompanionLayoutProps) {
  const stageRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const [layout, setLayout] = useState<CompanionGeometry>({
    stageHeight: 0,
    contentHeight: 0,
    toolbarHeight: 0,
  })
  const [animateLayout, setAnimateLayout] = useState(false)

  useLayoutEffect(() => {
    const stage = stageRef.current
    const content = contentRef.current
    if (!stage || !content) return

    const toolbar = content.firstElementChild
    const measure = () => {
      const stageHeight = Math.ceil(stage.getBoundingClientRect().height)
      const contentHeight = Math.ceil(content.getBoundingClientRect().height)
      const currentToolbar = content.firstElementChild
      const toolbarHeight = currentToolbar
        ? Math.ceil(currentToolbar.getBoundingClientRect().height) +
          Number.parseFloat(window.getComputedStyle(currentToolbar).marginBottom || '0')
        : 0

      setLayout((previous) =>
        previous.stageHeight === stageHeight &&
        previous.contentHeight === contentHeight &&
        previous.toolbarHeight === toolbarHeight
          ? previous
          : { stageHeight, contentHeight, toolbarHeight },
      )
    }

    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(stage)
    observer.observe(content)
    if (toolbar) observer.observe(toolbar)
    return () => observer.disconnect()
  }, [ready])

  useEffect(() => {
    if (!ready) return
    const timer = window.setTimeout(
      () => setAnimateLayout(true),
      motionDurationMs('--motion-companion-ready-delay'),
    )
    return () => window.clearTimeout(timer)
  }, [ready])

  // One measured stage determines the panel's maximum height, its vertical
  // alignment, and the divider's bounds. Never guess an independent vh offset.
  const panelAvailableHeight = Math.max(0, layout.stageHeight - layout.toolbarHeight - 8)
  const stageCenter = layout.stageHeight * (idle ? 0.42 : 0.5)
  const verticalOffset = Math.max(
    0,
    Math.min(layout.stageHeight - layout.contentHeight, stageCenter - layout.contentHeight / 2),
  )
  const dividerHeight = Math.max(
    0,
    Math.min(layout.contentHeight - 8, layout.stageHeight - verticalOffset - 8),
  )
  const motionClass = animateLayout
    ? 'transition-[margin-top] duration-[var(--motion-companion-reflow)] ease-[var(--motion-ease-settle)] motion-reduce:transition-none'
    : ''

  return (
    <div className="grid h-full min-h-0 min-w-0 grid-cols-[minmax(0,var(--reader-column-share))_var(--editorial-divider-thickness)_minmax(0,var(--companion-column-share))] grid-rows-[minmax(0,1fr)] items-stretch gap-x-6">
      <div className="min-h-0 min-w-0">{reader}</div>

      {/* The boundary belongs to the layout, not to either content column. */}
      <div className={motionClass} style={{ marginTop: verticalOffset }}>
        <VerticalEditorialDivider
          className={
            'mt-1 ' +
            (animateLayout
              ? 'transition-[height] duration-[var(--motion-companion-reflow)] ease-[var(--motion-ease-settle)] motion-reduce:transition-none'
              : '')
          }
          style={{ height: dividerHeight }}
        />
      </div>

      <div ref={stageRef} className="h-full min-h-0 min-w-0">
        <div className={'min-w-0 ' + motionClass} style={{ marginTop: verticalOffset }}>
          <div
            ref={contentRef}
            style={
              {
                '--companion-panel-max-height': `min(var(--companion-panel-default-max-height), ${panelAvailableHeight}px)`,
              } as CSSProperties
            }
          >
            {children}
          </div>
        </div>
      </div>
    </div>
  )
}
