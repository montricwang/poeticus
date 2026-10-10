/** Measure text only; CSS owns the minimum and maximum composer widths. */
export function composerWidthForLines(
  question: string,
  measureText: (text: string) => number,
): number {
  const longestLine = question
    .split(/\r?\n/)
    .reduce((widest, line) => Math.max(widest, measureText(line)), 0)

  // Textarea padding and a little room for the caret.
  return Math.ceil(longestLine + 32)
}
