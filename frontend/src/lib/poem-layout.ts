export type PoemLine = {
  text: string
  start: number
  end: number
  sourceGapBefore: boolean
}

export type PoemTextRun = {
  text: string
  punctuation: boolean
}

const LINE_ENDINGS = new Set(['，', ',', '。', '.', '！', '!', '？', '?'])
const CLOSING_MARKS = new Set(['”', '’', '」', '』', '）', '》', '】'])
const PUNCTUATION = /^[、，。；：！？,.!?;:]+$/u

function isNewline(character: string | undefined): boolean {
  return character === '\n' || character === '\r'
}

/**
 * Segments are only a reading layout, not a scholarly determination of stanza,
 * rhyme or syntax. Every source code unit occurs in exactly one returned line.
 */
export function buildPoemLines(source: string): PoemLine[] {
  const lines: PoemLine[] = []
  let start = 0
  let cursor = 0
  let sourceGapBefore = false

  function appendLine(end: number) {
    if (end <= start) return
    const text = source.slice(start, end)
    lines.push({ text, start, end, sourceGapBefore })
    sourceGapBefore = /(?:\r?\n[ \t]*){2,}$/u.test(text)
    start = end
  }

  while (cursor < source.length) {
    const character = source[cursor]

    if (LINE_ENDINGS.has(character)) {
      let end = cursor + 1
      // Keep ?!, …… and closing quotes with the verse they terminate.
      while (end < source.length && (LINE_ENDINGS.has(source[end]) || CLOSING_MARKS.has(source[end]))) {
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

/** Marks punctuation without changing the characters, order or source offsets. */
export function buildPoemTextRuns(line: string): PoemTextRun[] {
  return line
    .split(/([、，。；：！？,.!?;:]+)/u)
    .filter(Boolean)
    .map((text) => ({ text, punctuation: PUNCTUATION.test(text) }))
}
