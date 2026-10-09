import type { SelectedText } from '@/types/poem'

/**
 * 将浏览器中的文本选区映射到原始诗文的字符位置。
 *
 * 诗文正文由多个 DOM 文本节点组成，使用完整原文校验选区偏移。
 *
 * @param root 诗文正文容器，不包含标题和小序
 * @param range 浏览器选区，允许部分越过正文边界
 * @param source poemText() 返回的完整原文
 * @returns 选中文字及原文中的 [start, end) 位置（UTF-16）；
 *   无有效交集或无法准确映射时返回 null
 */
export function selectionFromPoemRange(
  root: HTMLElement,
  range: Range,
  source: string,
): SelectedText | null {
  // 引用位置以原文为准，DOM 中的正文文本必须与原文完全一致。
  if (root.textContent !== source) return null

  const bodyRange = document.createRange()
  bodyRange.selectNodeContents(root)

  if (
    range.compareBoundaryPoints(Range.START_TO_END, bodyRange) <= 0 ||
    range.compareBoundaryPoints(Range.END_TO_START, bodyRange) >= 0
  ) {
    return null
  }

  // 裁剪 Range 副本到正文范围，保留用户实际划选的区域。
  const clipped = range.cloneRange()
  if (clipped.compareBoundaryPoints(Range.START_TO_START, bodyRange) < 0) {
    clipped.setStart(root, 0)
  }
  if (clipped.compareBoundaryPoints(Range.END_TO_END, bodyRange) > 0) {
    clipped.setEnd(root, root.childNodes.length)
  }

  // 分别统计正文开头到选区起点、终点的字符数。
  // 取 DOM 节点文本长度，排除视觉分行在选区字符串中产生的额外换行。
  const prefix = document.createRange()
  prefix.selectNodeContents(root)
  prefix.setEnd(clipped.startContainer, clipped.startOffset)
  const start = prefix.cloneContents().textContent?.length ?? 0

  prefix.setEnd(clipped.endContainer, clipped.endOffset)
  const end = prefix.cloneContents().textContent?.length ?? 0
  const text = source.slice(start, end)

  return start < end && text.trim() ? { text, start, end } : null
}
