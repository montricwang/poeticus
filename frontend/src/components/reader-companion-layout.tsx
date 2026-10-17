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
  catalog: ReactNode
  children: ReactNode
  ready: boolean
  idle: boolean
  catalogOpen: boolean
  swapPhase: 'steady' | 'leaving' | 'arriving'
}

type CompanionGeometry = {
  stageHeight: number
  contentHeight: number
  toolbarHeight: number
}

/**
 * 固定双栏书页：竖线占据独立的 Grid 列，既不属于阅读器也不属于右栏内容。
 * 中线高度跟随当前右栏内容；目录打开时占用右侧整栏，不改变左侧位置。
 */
export function ReaderCompanionLayout({
  reader,
  catalog,
  children,
  ready,
  idle,
  catalogOpen,
  swapPhase,
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

    // 目录是同级覆盖层，不影响讨论区的高度或工具栏测量。
    const toolbar = content.querySelector('[role="group"][aria-label="讨论视图"]')
    const measure = () => {
      const stageHeight = Math.ceil(stage.getBoundingClientRect().height)
      const contentHeight = Math.ceil(content.getBoundingClientRect().height)
      const currentToolbar = content.querySelector('[role="group"][aria-label="讨论视图"]')
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

  // 统一使用测量出的舞台高度计算面板上限及纵向位置，
  // 不另外猜测一个以 vh 为单位的偏移量。
  const panelAvailableHeight = Math.max(0, layout.stageHeight - layout.toolbarHeight - 8)
  const stageCenter = layout.stageHeight * (idle ? 0.42 : 0.5)
  const verticalOffset = Math.max(
    0,
    Math.min(layout.stageHeight - layout.contentHeight, stageCenter - layout.contentHeight / 2),
  )
  const dividerHeight = catalogOpen
    ? Math.max(0, layout.stageHeight - 8)
    : Math.max(0, Math.min(layout.contentHeight - 8, layout.stageHeight - verticalOffset - 8))
  const motionClass = animateLayout
    ? 'transition-[margin-top] duration-[var(--motion-companion-reflow)] ease-[var(--motion-ease-settle)] motion-reduce:transition-none'
    : ''

  return (
    <div
      className="grid h-full min-h-0 min-w-0 grid-rows-[minmax(0,1fr)] items-stretch gap-x-6"
      style={{
        gridTemplateColumns:
          'minmax(0, var(--reader-column-share)) var(--editorial-divider-thickness) minmax(0, var(--companion-column-share))',
      }}
    >
      <div className="min-h-0 min-w-0">{reader}</div>

      {/* 中线是两栏的公共分隔；只由布局层测量和绘制。 */}
      <div className={motionClass} style={{ marginTop: catalogOpen ? 0 : verticalOffset }}>
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

      <div ref={stageRef} className="reader-companion-stage relative h-full min-h-0 min-w-0">
        <div className={'min-w-0 ' + motionClass} style={{ marginTop: verticalOffset }}>
          <div
            aria-hidden={catalogOpen}
            inert={catalogOpen}
            className={
              'transition-opacity duration-[var(--motion-catalog-switch)] ease-[var(--motion-ease-settle)] motion-reduce:transition-none ' +
              (catalogOpen ? 'pointer-events-none opacity-0' : 'opacity-100')
            }
          >
            <div
              ref={contentRef}
              className={
                'transition-opacity duration-[var(--motion-poem-swap)] ease-[var(--motion-ease-settle)] motion-reduce:transition-none ' +
                (swapPhase === 'steady' ? 'opacity-100' : 'opacity-0')
              }
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

        {/* 目录独立覆盖整个右栏；关闭时仍保持高度，完成淡出后再隐去。 */}
        <div
          aria-hidden={!catalogOpen}
          inert={!catalogOpen}
          className={
            'absolute inset-0 min-h-0 min-w-0 transition-opacity duration-[var(--motion-catalog-switch)] ease-[var(--motion-ease-settle)] motion-reduce:transition-none ' +
            (catalogOpen ? 'opacity-100' : 'pointer-events-none opacity-0')
          }
        >
          {catalog}
        </div>
      </div>
    </div>
  )
}
