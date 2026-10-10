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

type DesktopCompanionStageProps = {
  children: ReactNode
  ready: boolean
  idle: boolean
}

type CompanionLayout = {
  stageHeight: number
  contentHeight: number
  toolbarHeight: number
}

/**
 * The stage gets its real height from the shared desktop viewport layout.
 * Keep the chat/analysis panel within that height (minus its toolbar), and
 * center the current content only as far as the available space permits.
 */
export function DesktopCompanionStage({ children, ready, idle }: DesktopCompanionStageProps) {
  const stageRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const [layout, setLayout] = useState<CompanionLayout>({
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
      const toolbarHeight = toolbar
        ? Math.ceil(toolbar.getBoundingClientRect().height) +
          Number.parseFloat(window.getComputedStyle(toolbar).marginBottom || '0')
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
  }, [])

  useEffect(() => {
    if (!ready) return
    // Prevent an entrance transition while the first saved chat is measured.
    const timer = window.setTimeout(
      () => setAnimateLayout(true),
      motionDurationMs('--motion-companion-ready-delay'),
    )
    return () => window.clearTimeout(timer)
  }, [ready])

  // The toolbar and composer share the measured stage; the message/analysis
  // scrollport consumes only what remains. No second viewport-height guess.
  const panelAvailableHeight = Math.max(0, layout.stageHeight - layout.toolbarHeight - 8)
  // A fresh, empty companion sits slightly above the geometric midpoint.
  const stageCenter = layout.stageHeight * (idle ? 0.42 : 0.5)
  const verticalOffset = Math.max(
    0,
    Math.min(layout.stageHeight - layout.contentHeight, stageCenter - layout.contentHeight / 2),
  )
  const motionClass = animateLayout
    ? 'transition-[margin-top] duration-[var(--motion-companion-reflow)] ease-[var(--motion-ease-settle)] motion-reduce:transition-none'
    : ''
  const dividerHeight = Math.max(
    0,
    Math.min(layout.contentHeight - 8, layout.stageHeight - verticalOffset - 8),
  )

  return (
    <div
      ref={stageRef}
      className="grid h-full min-h-0 min-w-0 grid-cols-[1.5px_minmax(0,1fr)] items-start gap-x-6"
    >
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
  )
}
