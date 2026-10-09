import type { SelectedText } from '@/types/poem'

/**
 * 将浏览器中的文本选区映射到原始诗文的字符位置。
 *
 * 正文分行和标点样式会产生多个 DOM 文本节点，不能再依赖单个节点
 * 的字符偏移；映射结果始终以原文为准。
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
  // 防止显示层增删字符导致引用错位：DOM 文本必须与原文完全一致。
  if (root.textContent !== source) return null

  const bodyRange = document.createRange()
  bodyRange.selectNodeContents(root)

  if (
    range.compareBoundaryPoints(Range.START_TO_END, bodyRange) <= 0 ||
    range.compareBoundaryPoints(Range.END_TO_START, bodyRange) >= 0
  ) {
    return null
  }

  // 只裁剪选区的副本，不改变用户实际划选的范围。
  const clipped = range.cloneRange()
  if (clipped.compareBoundaryPoints(Range.START_TO_START, bodyRange) < 0) {
    clipped.setStart(root, 0)
  }
  if (clipped.compareBoundaryPoints(Range.END_TO_END, bodyRange) > 0) {
    clipped.setEnd(root, root.childNodes.length)
  }

  // 分别统计正文开头到选区起点、终点的字符数。
  // 不用 range.toString()：它可能包含视觉分行产生的额外换行符。
  const prefix = document.createRange()
  prefix.selectNodeContents(root)
  prefix.setEnd(clipped.startContainer, clipped.startOffset)
  const start = prefix.cloneContents().textContent?.length ?? 0

  prefix.setEnd(clipped.endContainer, clipped.endOffset)
  const end = prefix.cloneContents().textContent?.length ?? 0
  const text = source.slice(start, end)

  return start < end && text.trim() ? { text, start, end } : null
}
