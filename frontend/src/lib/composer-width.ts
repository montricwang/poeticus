/** 只测量输入文字宽度；输入区的最小和最大宽度由 CSS 控制。 */
export function composerWidthForLines(
  question: string,
  measureText: (text: string) => number,
): number {
  const longestLine = question
    .split(/\r?\n/)
    .reduce((widest, line) => Math.max(widest, measureText(line)), 0)

  // 额外预留 Textarea 内边距和光标空间。
  return Math.ceil(longestLine + 32)
}
