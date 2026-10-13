import type { ReactNode } from 'react'

import { ViewToolbar, type ActiveView } from '@/components/view-toolbar'
import { ViewToolbarDivider } from '@/components/view-toolbar-divider'

type CompanionPaneProps = {
  activeView: ActiveView
  onViewChange: (view: ActiveView) => void
  fillAvailableHeight: boolean
  fadingOut: boolean
  children: ReactNode
}

/**
 * 组织视图切换、分隔线与当前面板内容。
 * 使用 Fragment 保持 ReaderCompanionLayout 所测量的 DOM 结构：
 * 首个子元素仍是 ViewToolbar，不增加可能裁剪内容的包装节点。
 */
export function CompanionPane({
  activeView,
  onViewChange,
  fillAvailableHeight,
  fadingOut,
  children,
}: CompanionPaneProps) {
  return (
    <>
      <ViewToolbar activeView={activeView} onViewChange={onViewChange} />
      <ViewToolbarDivider />
      <div
        className={
          'min-w-0 transition-opacity duration-[var(--motion-view-fade)] ease-in-out motion-reduce:transition-none ' +
          (fillAvailableHeight ? 'flex min-h-0 flex-1 flex-col ' : '') +
          (fadingOut ? 'opacity-0' : 'opacity-100')
        }
      >
        {children}
      </div>
    </>
  )
}
