import { ArrowLeft, MessageCircle, PanelLeft } from 'lucide-react'
import type { ReactNode, RefObject } from 'react'

import { Button } from '@/components/ui/button'
import { ThemeSwitcher } from '@/components/theme-switcher'
import { AuthControls } from '@/components/auth-controls'
import { MobileDiscussionScreen } from '@/components/mobile-discussion-screen'
import type { LayoutCatalog, LayoutReader } from '@/components/page-layout-props'

type MobileLayoutProps = {
  catalog: LayoutCatalog
  reader: LayoutReader
  onGoHome: () => void
  catalogToggleRef: RefObject<HTMLButtonElement | null>
  readerScrollRef: RefObject<HTMLDivElement | null>
  discussion: {
    content: ReactNode
    open: boolean
    onOpen: () => void
    onClose: () => void
    hasSelection: boolean
    hasUnreadReply: boolean
  }
}

/** 窄屏阅读、讨论与目录抽屉的页面结构；业务状态仍由 App 维护。 */
export function MobileLayout({
  catalog,
  reader,
  discussion,
  onGoHome,
  catalogToggleRef,
  readerScrollRef,
}: MobileLayoutProps) {
  return (
    <>
      <header className="shrink-0 border-b border-border/50">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 md:px-8">
          {!discussion.open ? (
            <>
              <div className="flex items-center gap-2">
                <Button
                  ref={catalogToggleRef}
                  type="button"
                  size="icon"
                  variant="ghost"
                  aria-label={catalog.open ? '收起作品目录' : '展开作品目录'}
                  aria-controls="poem-catalog"
                  aria-expanded={catalog.open}
                  onClick={catalog.onToggle}
                >
                  <PanelLeft className="size-5" aria-hidden="true" />
                </Button>
                <button
                  type="button"
                  onClick={onGoHome}
                  className="text-lg font-semibold tracking-tight hover:opacity-65 focus-visible:rounded-sm focus-visible:outline-2 focus-visible:outline-ring"
                >
                  Poeticus
                </button>
              </div>
              <div className="flex items-center gap-2">
                <ThemeSwitcher />
                <AuthControls />
              </div>
            </>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  aria-label="返回阅读"
                  onClick={discussion.onClose}
                >
                  <ArrowLeft className="size-5" aria-hidden="true" />
                </Button>
                <span className="text-base font-semibold tracking-tight">阅读讨论</span>
              </div>
              <AuthControls />
            </>
          )}
        </div>
      </header>
      <main className="relative min-h-0 flex-1 overflow-hidden">
        <section
          aria-label="诗词阅读"
          aria-hidden={discussion.open}
          inert={discussion.open || catalog.open}
          className={
            'absolute inset-0 z-10 bg-background ' +
            'md:transition-transform md:duration-[var(--motion-discussion-tablet-slide)] md:ease-[var(--motion-ease-settle)] ' +
            'motion-reduce:transition-none ' +
            (discussion.open ? 'md:-translate-x-full' : 'md:translate-x-0')
          }
        >
          {/* 给底部正文留出空间，避免被悬浮的讨论按钮遮挡。 */}
          <div
            className={
              'poeticus-scrollport poeticus-reader-scrollport h-full overflow-y-auto overscroll-contain px-5 pb-24 pt-7 md:px-8 ' +
              (reader.hasContentAbove ? 'poeticus-scroll-fade-top ' : '') +
              (reader.hasContentBelow ? 'poeticus-scroll-fade-bottom' : '')
            }
            ref={readerScrollRef}
            onScroll={(event) => reader.onScroll(event.currentTarget)}
          >
            {reader.switchError && (
              <div role="alert" className="mb-3 text-sm text-destructive">
                作品切换失败：{reader.switchError}。原作品仍可阅读，请重新选择。
              </div>
            )}

            <div className="relative min-w-0" aria-busy={reader.switching}>
              <div inert={reader.switching} className={reader.transitionClass}>
                {reader.content}
              </div>
            </div>
          </div>

          {reader.ready && (
            <Button
              type="button"
              size="lg"
              variant="outline"
              className="absolute right-4 bottom-[calc(3.5rem+env(safe-area-inset-bottom))] z-20 rounded-md bg-background/95 px-4 shadow-sm backdrop-blur-sm"
              aria-controls="mobile-discussion-screen"
              aria-expanded={discussion.open}
              aria-label={discussion.hasSelection ? '打开讨论并使用已选诗句提问' : '打开阅读讨论'}
              onClick={discussion.onOpen}
            >
              <MessageCircle className="size-4" aria-hidden="true" />
              <span>{discussion.hasSelection ? '提问' : '对话'}</span>
              {discussion.hasUnreadReply && (
                <span className="size-2 rounded-full bg-editorial-red" aria-label="有新回复" />
              )}
            </Button>
          )}
        </section>

        <MobileDiscussionScreen open={discussion.open}>
          <div className="flex min-h-0 flex-1 flex-col">{discussion.content}</div>
        </MobileDiscussionScreen>

        <div
          aria-hidden={!catalog.open}
          inert={!catalog.open}
          className={
            'absolute inset-0 z-40 transition-opacity duration-[var(--motion-catalog-phone-fade)] ' +
            'ease-[var(--motion-ease-settle)] motion-reduce:transition-none ' +
            'md:transition-none md:opacity-100 ' +
            (catalog.open ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0')
          }
        >
          <button
            type="button"
            tabIndex={-1}
            aria-label="关闭作品目录遮罩"
            className={
              'absolute inset-0 bg-black/55 md:transition-opacity md:duration-[var(--motion-catalog-backdrop-fade)] ' +
              'md:ease-[var(--motion-ease-settle)] motion-reduce:transition-none ' +
              (catalog.open
                ? 'pointer-events-auto md:opacity-100'
                : 'pointer-events-none md:opacity-0')
            }
            onClick={catalog.onClose}
          />

          <div
            className={
              'relative h-full w-screen md:w-[min(88vw,420px)] ' +
              'md:transform md:transition-transform md:duration-[var(--motion-catalog-drawer-slide)] ' +
              'md:ease-[var(--motion-ease-settle)] motion-reduce:transition-none ' +
              (catalog.open
                ? 'pointer-events-auto md:translate-x-0'
                : 'pointer-events-none md:-translate-x-full')
            }
          >
            {catalog.content}
          </div>
        </div>
      </main>
    </>
  )
}
