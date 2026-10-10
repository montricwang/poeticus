import type { ReactElement } from 'react'
import { Tooltip } from 'radix-ui'

type ActionTooltipProps = {
  label: string
  children: ReactElement
}

/**
 * 图标操作的浮动说明：使用 Portal 避开聊天滚动容器的裁剪，
 * 同时保留按钮本身的 aria-label 供辅助技术识别。
 */
export function ActionTooltip({ label, children }: ActionTooltipProps) {
  return (
    <Tooltip.Provider delayDuration={300} skipDelayDuration={150}>
      <Tooltip.Root>
        <Tooltip.Trigger asChild>{children}</Tooltip.Trigger>
        <Tooltip.Portal>
          <Tooltip.Content
            side="bottom"
            sideOffset={6}
            className="z-50 max-w-64 rounded-md bg-foreground px-2.5 py-1 text-xs font-medium text-background shadow-sm animate-in fade-in duration-[var(--motion-tooltip-enter)] motion-reduce:animate-none"
          >
            {label}
          </Tooltip.Content>
        </Tooltip.Portal>
      </Tooltip.Root>
    </Tooltip.Provider>
  )
}
