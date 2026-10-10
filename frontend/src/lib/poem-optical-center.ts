/**
 * 用诗行可见正文计算重心；只排除结尾的句读和紧随其后的闭合符号。
 * 行内标点仍参与测量，源文本和实际展示内容均保持不变。
 */
export function inkTextLength(line: string): number {
  const visible = line.trimEnd()
  const trailing = visible.match(/[，。！？,.!?;:；：、]+[”’」』））》】]*$/u)
  return visible.length - (trailing?.[0].length ?? 0)
}

export type InkMeasure = {
  /** 相对文本块左边缘的实际文字起点，未来可包含行缩进。 */
  start: number
  width: number
}

/**
 * 每行的可见正文宽度同时充当质量权重；将质心移到容器中心。
 * 平移限制在左右空白范围内，完整诗行仍处于可用阅读区域。
 */
export function opticalCenterOffset(
  measures: readonly InkMeasure[],
  blockWidth: number,
  availableWidth: number,
): number {
  if (
    !Number.isFinite(blockWidth) ||
    !Number.isFinite(availableWidth) ||
    blockWidth <= 0 ||
    availableWidth <= 0
  ) {
    return 0
  }

  let totalWeight = 0
  let weightedCenter = 0
  for (const { start, width } of measures) {
    if (!Number.isFinite(start) || !Number.isFinite(width) || start < 0 || width <= 0) {
      continue
    }
    totalWeight += width
    weightedCenter += width * (start + width / 2)
  }
  if (totalWeight === 0) return 0

  const desired = blockWidth / 2 - weightedCenter / totalWeight
  const safeSpace = Math.max(0, (availableWidth - blockWidth) / 2)
  return Math.max(-safeSpace, Math.min(safeSpace, desired))
}
