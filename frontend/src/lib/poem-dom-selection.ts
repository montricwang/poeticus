import type { SelectedText } from '@/types/poem'

/**
 * 将浏览器 DOM Range 转成原文里的选词结果，不再假设正文是单个文本节点。
 * root：只包含正文的 DOM 容器；range：浏览器选区（可能越过正文边缘）；
 * source：poemText() 得到的完整原文，是唯一可信的引用来源。
 * 返回 { text, start, end }，其中 start/end 是 UTF-16 [start, end)；
 * 不相交、空选区或 DOM 与原文不一致时返回 null。
 */
export function selectionFromPoemRange(
  root: HTMLElement,
  range: Range,
  source: string,
): SelectedText | null {
  // 核心不变量：DOM 里所有可见文字节点的串接必须严格等于 source。
  // 若排版时错误增删字符，宁可拒绝引用也不能默默给出错误偏移。
  if (root.textContent !== source) return null

  // 与正文无交集就立即退出，例如用户只选中了作品标题。
  const bodyRange = document.createRange()
  bodyRange.selectNodeContents(root)

  if (
    range.compareBoundaryPoints(Range.START_TO_END, bodyRange) <= 0 ||
    range.compareBoundaryPoints(Range.END_TO_START, bodyRange) >= 0
  ) {
    return null
  }

  // 只裁剪 Range 副本，不改变用户在页面上的真实选中范围。
  const clipped = range.cloneRange()
  if (clipped.compareBoundaryPoints(Range.START_TO_START, bodyRange) < 0) {
    clipped.setStart(root, 0)
  }
  if (clipped.compareBoundaryPoints(Range.END_TO_END, bodyRange) > 0) {
    clipped.setEnd(root, root.childNodes.length)
  }

  // 从正文开头数到选区起/止点；cloneContents().textContent 不计算
  // CSS display:block 带来的视觉换行，得到的长度与 source 的 UTF-16 下标一致。
  const prefix = document.createRange()
  prefix.selectNodeContents(root)
  prefix.setEnd(clipped.startContainer, clipped.startOffset)
  const start = prefix.cloneContents().textContent?.length ?? 0

  prefix.setEnd(clipped.endContainer, clipped.endOffset)
  const end = prefix.cloneContents().textContent?.length ?? 0
  const text = source.slice(start, end)

  // trim 只用来判断是否全为空白；返回的 text 不丢原始空格和换行。
  return start < end && text.trim() ? { text, start, end } : null
}
