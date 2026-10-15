import type { ReactNode } from 'react'

/** Catalog and reader are owned by App; page shells only choose their placement. */
export type LayoutCatalog = {
  content: ReactNode
  open: boolean
  onToggle: () => void
  onClose: () => void
}

export type LayoutReader = {
  content: ReactNode
  onScroll: (element: HTMLDivElement) => void
  hasContentAbove: boolean
  hasContentBelow: boolean
  ready: boolean
  switching: boolean
  switchError: string
  transitionClass: string
}
