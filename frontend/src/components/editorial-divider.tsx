import type { CSSProperties } from 'react'

import { cn } from '@/lib/utils'

type EditorialDividerProps = {
  className?: string
  style?: CSSProperties
}

/** 内容层次沿用书页式分隔，横竖均为 1.5px。 */
export function HorizontalEditorialDivider({ className, style }: EditorialDividerProps) {
  return (
    <div
      aria-hidden="true"
      className={cn('pointer-events-none h-[1.5px] shrink-0 bg-border/80', className)}
      style={style}
    />
  )
}

/** 两栏边界可独立微调厚度，不影响章节内横线。 */
export function VerticalEditorialDivider({ className, style }: EditorialDividerProps) {
  return (
    <div
      aria-hidden="true"
      className={cn('pointer-events-none w-[1.5px] shrink-0 bg-border/80', className)}
      style={style}
    />
  )
}
