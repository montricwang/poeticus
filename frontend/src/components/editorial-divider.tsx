import type { CSSProperties } from 'react'

import { cn } from '@/lib/utils'

type EditorialDividerProps = {
  className?: string
  style?: CSSProperties
}

/** Shared editorial rule. Geometry comes from one CSS token. */
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

/** Vertical editorial rule with the same geometric thickness. */
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
