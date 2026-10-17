/** 首页展示专用：跨诗行/断列识别成对书名号，不修改源文本。 */
export type HomeBookTitleRun = {
  text: string
  kind: 'text' | 'title' | 'marker'
}

/**
 * 先识别整段文字中的书名，再按原来的显示块分配样式。
 * 不完整的《或》保持原样；完整书名跨列时，每列都能续上书名线。
 */
export function buildHomeBookTitleRuns(chunks: readonly string[]): HomeBookTitleRun[][] {
  const source = chunks.join('')
  const kinds = new Uint8Array(source.length)

  for (const match of source.matchAll(/《[^《》]+》/gu)) {
    const start = match.index
    const end = start + match[0].length
    kinds[start] = 2
    kinds.fill(1, start + 1, end - 1)
    kinds[end - 1] = 2
  }

  let sourceOffset = 0
  return chunks.map((chunk) => {
    const runs: HomeBookTitleRun[] = []
    for (const char of chunk) {
      const kind = (['text', 'title', 'marker'] as const)[kinds[sourceOffset]]
      const previous = runs[runs.length - 1]
      if (previous?.kind === kind) {
        previous.text += char
      } else {
        runs.push({ text: char, kind })
      }
      sourceOffset += char.length
    }
    return runs
  })
}
