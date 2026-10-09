/**
 * 一条视觉诗行和原文对应关系。
 * start/end 是 UTF-16 [start, end)（含来源换行字符）；sourceGapBefore
 * 仅表示前一行末尾存在来源双换行，不保证它就是词作上下阕。
 */
export type PoemLine = {
  text: string
  start: number
  end: number
  sourceGapBefore: boolean
}

/** 一段原样文字；punctuation 只控制 CSS 样式，不改变字符内容。 */
export type PoemTextRun = {
  text: string
  punctuation: boolean
}

// 断行规则是阅读版式选择，不代表考证后的句法或韵脚。
const LINE_ENDINGS = new Set(['，', ',', '。', '.', '！', '!', '？', '?'])
// 右引号等闭合符号应随前一个句末标点留在同一行。
const CLOSING_MARKS = new Set(['”', '’', '」', '』', '）', '》', '】'])
// 独立着色标点与断行标点不同：顿号着色，但不在它后面强制换行。
const PUNCTUATION = /^[、，。；：！？,.!?;:]+$/u

/** 识别 CR/LF，不做有损换行规范化。 */
function isNewline(character: string | undefined): boolean {
  return character === '\n' || character === '\r'
}

/**
 * 把完整原文 source 切成视觉诗行，保留所有字符及 UTF-16 位置。
 * 返回的各行相邻、顺序不变：拼接全部 line.text 必须严格等于 source。
 * 仅用于排版，不推断词作上下阕或韵律结构。
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
 * 后续字体、标点间距调整都应局限在展示层。
 */
export function buildPoemTextRuns(line: string): PoemTextRun[] {
  return line
    .split(/([、，。；：！？,.!?;:]+)/u)
    .filter(Boolean)
    .map((text) => ({ text, punctuation: PUNCTUATION.test(text) }))
}
