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
 * Owns the view switch, its boundary, and the currently visible content.
 * A fragment preserves the DOM structure measured by ReaderCompanionLayout:
 * its first child remains ViewToolbar, with no extra clipping wrapper.
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
