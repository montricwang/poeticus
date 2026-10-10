/** Width follows the longest typed line, then caps at the editorial column width. */
export function composerWidthForLines(
  question: string,
  measureText: (text: string) => number,
): number {
  const longestLine = question
    .split(/\r?\n/)
    .reduce((widest, line) => Math.max(widest, measureText(line)), 0)

  // 32px allows for the input's side padding and caret breathing room.
  return Math.min(608, Math.max(288, Math.ceil(longestLine + 32)))
}
