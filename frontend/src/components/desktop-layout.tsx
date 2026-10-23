import { PanelRight } from 'lucide-react'
import type { ReactNode, RefObject } from 'react'

import { Button } from '@/components/ui/button'
import { ThemeSwitcher } from '@/components/theme-switcher'
import { AuthControls } from '@/components/auth-controls'
import { ReaderCompanionLayout } from '@/components/reader-companion-layout'
import { ReaderPane } from '@/components/reader-pane'
import type { LayoutCatalog, LayoutReader } from '@/components/page-layout-props'

type DesktopLayoutProps = {
  catalog: LayoutCatalog
  reader: LayoutReader
  onGoHome: () => void
  catalogToggleRef: RefObject<HTMLButtonElement | null>
  readerScrollRef: RefObject<HTMLDivElement | null>
  discussion: ReactNode
  navigation: ReactNode
  idle: boolean
  swapPhase: 'steady' | 'leaving' | 'arriving'
}

/** 桌面固定双栏与目录覆盖层的组装，不持有作品或聊天状态。 */
export function DesktopLayout({
  catalog,
  reader,
  onGoHome,
  catalogToggleRef,
  readerScrollRef,
  discussion,
  navigation,
  idle,
  swapPhase,
}: DesktopLayoutProps) {
  return (
    <>
      <header className="shrink-0 border-b border-border/50">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 md:px-8">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onGoHome}
              className="text-lg font-semibold tracking-tight hover:opacity-65 focus-visible:rounded-sm focus-visible:outline-2 focus-visible:outline-ring"
            >
              Poeticus
            </button>
          </div>
          <div className="flex items-center gap-2">
            <Button
              ref={catalogToggleRef}
              type="button"
              size="sm"
              variant="ghost"
              aria-label={catalog.open ? '收起作品目录' : '展开作品目录'}
              aria-controls="poem-catalog"
              aria-expanded={catalog.open}
              onClick={catalog.onToggle}
            >
              <PanelRight className="size-4" aria-hidden="true" />
              目录
            </Button>
            <ThemeSwitcher />
            <AuthControls />
          </div>
        </div>
      </header>
      <main className="mx-auto flex min-h-0 w-full max-w-(--desktop-shell-max-width) flex-1 flex-col overflow-hidden px-5 pb-7 pt-7 md:px-8">
        {/* 目录与讨论共用右栏；两栏和中线的横向位置不受目录开关影响。 */}
        <div className="mx-auto h-full w-full min-h-0 min-w-0 max-w-[var(--reading-stage-max-width)]">
          <div className="relative h-full min-h-0 min-w-0" aria-busy={reader.switching}>
            {reader.switchError && (
              <div role="alert" className="mb-3 text-sm text-destructive">
                作品切换失败：{reader.switchError}。原作品仍可阅读，请重新选择。
              </div>
            )}

            <div inert={reader.switching} className="h-full min-h-0 min-w-0">
              <ReaderCompanionLayout
                ready={reader.ready}
                idle={idle}
                catalogOpen={catalog.open}
                catalog={catalog.content}
                swapPhase={swapPhase}
                reader={
                  <ReaderPane
                    scrollRef={readerScrollRef}
                    onScroll={reader.onScroll}
                    hasContentAbove={reader.hasContentAbove}
                    hasContentBelow={reader.hasContentBelow}
                    poemTransitionClass={reader.transitionClass}
                    navigation={navigation}
                  >
                    {reader.content}
                  </ReaderPane>
                }
              >
                {discussion}
              </ReaderCompanionLayout>
            </div>
          </div>
        </div>
      </main>
    </>
  )
}
