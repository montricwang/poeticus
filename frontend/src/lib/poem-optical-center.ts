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
 * 根据诗行宽度分布，决定从传统居中向视觉质心靠近多少。
 * 平均行宽与最长行宽的比值兼顾长短句及其出现次数，避免固定修正比例。
 */
export function adaptiveOpticalStrength(measures: readonly InkMeasure[]): number {
  let count = 0
  let totalWidth = 0
  let maxWidth = 0
  for (const { start, width } of measures) {
    if (!Number.isFinite(start) || !Number.isFinite(width) || start < 0 || width <= 0) {
      continue
    }
    count += 1
    totalWidth += width
    maxWidth = Math.max(maxWidth, width)
  }
  if (count === 0 || maxWidth === 0) return 0
  return totalWidth / (count * maxWidth)
}

/**
 * 每行的可见正文宽度同时充当质量权重；将质心移到容器中心。
 * strength 控制从原有最长行居中向纯质心居中靠近的比例：
 * 0 保持原位置，1 完全按质心修正。最后限制在可用余白之内。
 */
export function opticalCenterOffset(
  measures: readonly InkMeasure[],
  blockWidth: number,
  availableWidth: number,
  strength = 1,
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

  const safeSpace = Math.max(0, (availableWidth - blockWidth) / 2)
  // 只缩小原本的质心修正量；相同句长分布在不同屏宽下不会额外产生固定左偏。
  const ratio = Number.isFinite(strength) ? Math.max(0, Math.min(1, strength)) : 1
  const desired = (blockWidth / 2 - weightedCenter / totalWeight) * ratio
  return Math.max(-safeSpace, Math.min(safeSpace, desired))
}
