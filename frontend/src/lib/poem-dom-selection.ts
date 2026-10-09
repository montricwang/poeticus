import type { SelectedText } from '@/types/poem'

/**
 * Read offsets from DOM text content, not Range.toString(), which can reflect visual
 * line breaks that were never part of the canonical poem.
 */
export function selectionFromPoemRange(
  root: HTMLElement,
  range: Range,
  source: string,
): SelectedText | null {
  // All displayed text nodes must reproduce the original source in order.
  // Never silently return a potentially wrong citation if the rendering drifts.
  if (root.textContent !== source) return null

  const bodyRange = document.createRange()
  bodyRange.selectNodeContents(root)

  if (
    range.compareBoundaryPoints(Range.START_TO_END, bodyRange) <= 0 ||
    range.compareBoundaryPoints(Range.END_TO_START, bodyRange) >= 0
  ) {
    return null
  }

  const clipped = range.cloneRange()
  if (clipped.compareBoundaryPoints(Range.START_TO_START, bodyRange) < 0) {
    clipped.setStart(root, 0)
  }
  if (clipped.compareBoundaryPoints(Range.END_TO_END, bodyRange) > 0) {
    clipped.setEnd(root, root.childNodes.length)
  }

  const prefix = document.createRange()
  prefix.selectNodeContents(root)
  prefix.setEnd(clipped.startContainer, clipped.startOffset)
  const start = prefix.cloneContents().textContent?.length ?? 0

  prefix.setEnd(clipped.endContainer, clipped.endOffset)
  const end = prefix.cloneContents().textContent?.length ?? 0
  const text = source.slice(start, end)

  return start < end && text.trim() ? { text, start, end } : null
}
