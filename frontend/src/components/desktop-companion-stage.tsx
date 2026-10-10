import { useLayoutEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'

import { VerticalEditorialDivider } from '@/components/editorial-divider'

type DesktopCompanionStageProps = {
  children: ReactNode
}

/**
 * 右侧阅读助手的内容高度决定分割线长度；历史最高高度决定按钮的顶部基准。
 * 这样内容增长时控件逐渐上移，切换到较短的视图也不会把控件重新推到下方。
 * 父层通过 key={poemId} 在切换作品时重置这个基准。
 */
export function DesktopCompanionStage({ children }: DesktopCompanionStageProps) {
  const contentRef = useRef<HTMLDivElement>(null)
  const [currentHeight, setCurrentHeight] = useState(0)
  const [reservedHeight, setReservedHeight] = useState(0)

  useLayoutEffect(() => {
    const content = contentRef.current
    if (!content) return

    const observer = new ResizeObserver(() => {
      const height = Math.ceil(content.getBoundingClientRect().height)
      setCurrentHeight((previous) => (previous === height ? previous : height))
      setReservedHeight((previous) => Math.max(previous, height))
    })
    observer.observe(content)
    return () => observer.disconnect()
  }, [])

  // 始于按钮组附近，向下延伸至当前视图（含聊天输入框）的底部。
  // 空视图保留一段短线；长对话的消息区域自行滚动，不再人为截断竖线。
  const dividerHeight = Math.max(176, currentHeight - 8)

  return (
    <div className="grid min-h-[var(--desktop-reading-stage-min-height)] min-w-0 grid-cols-[1.5px_minmax(0,1fr)] gap-x-6">
      <div className="flex min-w-0 items-start">
        <div className="my-auto w-[1.5px]" style={{ minHeight: reservedHeight || undefined }}>
          <VerticalEditorialDivider className="mt-1" style={{ height: dividerHeight }} />
        </div>
      </div>
      <div className="flex min-w-0 items-start">
        <div className="my-auto w-full min-w-0" style={{ minHeight: reservedHeight || undefined }}>
          <div ref={contentRef}>{children}</div>
        </div>
      </div>
    </div>
  )
}
