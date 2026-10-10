/**
 * 一条视觉诗行和原文对应关系。
 * start/end 是 UTF-16 [start, end)（含来源换行字符）；sourceGapBefore
 * 表示前一行末尾存在来源双换行，用于显示段间留白。
 */
export type PoemLine = {
  text: string
  start: number
  end: number
  sourceGapBefore: boolean
}

/** 连续的原文片段；punctuation 标记它是否采用标点样式。 */
export type PoemTextRun = {
  text: string
  punctuation: boolean
}

// 阅读器在这些标点后结束视觉诗行。
const LINE_ENDINGS = new Set(['，', ',', '。', '.', '！', '!', '？', '?'])
// 右引号等闭合符号应随前一个句末标点留在同一行。
const CLOSING_MARKS = new Set(['”', '’', '」', '』', '）', '》', '】'])
// 标点样式兼顾中文书名号、各种引号与缺字方框；断行仍只按 LINE_ENDINGS。
const PUNCTUATION_MARKS = /([\p{P}□■▢〓�]+)/u
const PUNCTUATION = /^[\p{P}□■▢〓�]+$/u

/** 识别原文中的 CR 与 LF 换行字符。 */
function isNewline(character: string | undefined): boolean {
  return character === '\n' || character === '\r'
}

/**
 * 把完整原文 source 切成视觉诗行，保留所有字符及 UTF-16 位置。
 * 返回的各行相邻、顺序不变：拼接全部 line.text 必须严格等于 source。
 * 这里的行边界用于视觉排版，来源段间留白另由 sourceGapBefore 记录。
 */
export function buildPoemLines(source: string): PoemLine[] {
  const lines: PoemLine[] = []
  // 扫描位置和行边界全部使用 JS 字符串的 UTF-16 下标。
  let start = 0
  let cursor = 0
  let sourceGapBefore = false

  /**
   * 保存 [start, end) 的原文，再根据当前行尾的真实换行符，
   * 决定下一条视觉诗行之前是否需要额外留白。
   */
  function appendLine(end: number) {
    if (end <= start) return
    const text = source.slice(start, end)
    lines.push({ text, start, end, sourceGapBefore })
    sourceGapBefore = /(?:\r?\n[ \t]*){2,}$/u.test(text)
    start = end
  }

  // 标点和来源换行会结束一行，其余字符只向前移动游标。
  while (cursor < source.length) {
    const character = source[cursor]

    if (LINE_ENDINGS.has(character)) {
      let end = cursor + 1
      // Keep ?!, …… and closing quotes with the verse they terminate.
      while (
        end < source.length &&
        (LINE_ENDINGS.has(source[end]) || CLOSING_MARKS.has(source[end]))
      ) {
        end += 1
      }
      // An explicit source line break after punctuation already marks the next line.
      while (end < source.length && isNewline(source[end])) end += 1
      appendLine(end)
      cursor = end
    } else if (isNewline(character)) {
      let end = cursor + 1
      while (end < source.length && isNewline(source[end])) end += 1
      appendLine(end)
      cursor = end
    } else {
      cursor += 1
    }
  }

  appendLine(source.length)
  return lines
}

/**
 * 将视觉诗行 line 切成普通文字与可弱化标点片段。
 * 捕获组使 split 不丢标点；返回片段依次拼接必须完全等于 line。
 * 字体、颜色与标点间距由展示层控制。
 */
export function buildPoemTextRuns(line: string): PoemTextRun[] {
  return line
    .split(PUNCTUATION_MARKS)
    .filter(Boolean)
    .map((text) => ({ text, punctuation: PUNCTUATION.test(text) }))
}
