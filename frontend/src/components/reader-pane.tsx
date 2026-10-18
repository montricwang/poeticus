import type { ReactNode, RefObject } from 'react'

import { HorizontalEditorialDivider } from '@/components/editorial-divider'

type ReaderPaneProps = {
  children: ReactNode
  navigation?: ReactNode
  scrollRef: RefObject<HTMLDivElement | null>
  onScroll: (element: HTMLDivElement) => void
  hasContentAbove: boolean
  hasContentBelow: boolean
  poemTransitionClass: string
}

/**
 * 管理桌面阅读区的滚动容器及其与篇目导航之间的边界。
 * 分隔线独立于 ReaderNavigation，不受导航按钮样式影响，
 * 也不会被正文滚动容器裁剪。
 */
export function ReaderPane({
  children,
  navigation,
  scrollRef,
  onScroll,
  hasContentAbove,
  hasContentBelow,
  poemTransitionClass,
}: ReaderPaneProps) {
  return (
    <div className="relative flex h-full min-h-0 min-w-0 flex-col">
      <div
        className={
          'poeticus-scrollport poeticus-reader-scrollport flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto overscroll-contain px-1 ' +
          (hasContentAbove ? 'poeticus-scroll-fade-top ' : '') +
          (hasContentBelow ? 'poeticus-scroll-fade-bottom' : '')
        }
        ref={scrollRef}
        onScroll={(event) => onScroll(event.currentTarget)}
      >
        <div className={poemTransitionClass + ' lg:flex lg:flex-1 lg:flex-col'}>{children}</div>
      </div>
      {navigation && (
        <footer className="mx-auto mt-6 w-full shrink-0 px-0 pb-4 lg:mt-auto lg:max-w-(--reader-footer-max-width) lg:px-4 lg:pt-8 lg:pb-0">
          <HorizontalEditorialDivider className="mb-3 hidden w-full lg:block" />
          {navigation}
        </footer>
      )}
    </div>
  )
}
