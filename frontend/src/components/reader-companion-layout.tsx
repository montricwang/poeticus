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
 * 管理阅读区和伴读区的分界。分隔线与两侧内容处于同一级 Grid，
 * 不嵌入伴读内容，因此不会受到内部滚动裁剪、透明度动画或文本排版影响。
 *
 * 只测量伴读内容的实际尺寸，并据此统一计算面板位置及分隔线的位置和高度。
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

    // CompanionPane 使用 Fragment，首个 DOM 子元素必须是 ViewToolbar；
    // 如果新增包装元素，这里的工具栏高度测量也必须同步调整。
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

  // 统一使用测量出的舞台高度计算面板上限、纵向位置及分隔线边界，
  // 不另外猜测一个以 vh 为单位的偏移量。
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
    <div
      className="grid h-full min-h-0 min-w-0 grid-rows-[minmax(0,1fr)] items-stretch gap-x-6"
      style={{
        gridTemplateColumns:
          'minmax(0, var(--reader-column-share)) var(--editorial-divider-thickness) minmax(0, var(--companion-column-share))',
      }}
    >
      <div className="min-h-0 min-w-0">{reader}</div>

      {/* 分隔线归布局组件管理，不属于任一侧内容列。 */}
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
