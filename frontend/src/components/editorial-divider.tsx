import type { CSSProperties } from 'react'

import { cn } from '@/lib/utils'

type EditorialDividerProps = {
  className?: string
  style?: CSSProperties
}

/** 通用横向分隔线，厚度由统一 CSS 变量控制。 */
export function HorizontalEditorialDivider({ className, style }: EditorialDividerProps) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        'pointer-events-none h-[var(--editorial-divider-thickness)] shrink-0 bg-border/80',
        className,
      )}
      style={style}
    />
  )
}

/** 纵向分隔线，与横向分隔线保持相同厚度。 */
export function VerticalEditorialDivider({ className, style }: EditorialDividerProps) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        'pointer-events-none w-[var(--editorial-divider-thickness)] shrink-0 bg-border/80',
        className,
      )}
      style={style}
    />
  )
}
