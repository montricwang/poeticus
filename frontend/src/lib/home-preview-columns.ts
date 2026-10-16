const SENTENCE_END = /[。！？!?]$/u
const CLAUSE_END = /[，、；;：:]$/u
const CLOSING_MARK = /^[，。！？!?、；;：:）》」』]$/u
const PAUSE_MARK = /^[，。！？!?、；;：:]$/u
const BODY_CHAR = /^[^\p{P}\s]$/u
const SINGLE_CHARACTER_FRAGMENT_PENALTY = 100

/**
 * 断行时不让一个句读单位在行首或行尾只剩一个正文字符。
 * 比如「...腮｜雪。懒起...」与「关河冷落，残｜照当楼...」。
 * 必须验证断点另一侧还有正文，避免误伤原文确实只有一字的短句。
 */
function danglingCharacterPenalty(chars: string[], start: number, end: number): number {
  const oneCharBeforePause =
    start > 0 &&
    BODY_CHAR.test(chars[start - 1]) &&
    BODY_CHAR.test(chars[start] ?? '') &&
    PAUSE_MARK.test(chars[start + 1] ?? '')

  const oneCharAfterPause =
    end < chars.length &&
    PAUSE_MARK.test(chars[end - 2] ?? '') &&
    BODY_CHAR.test(chars[end - 1] ?? '') &&
    BODY_CHAR.test(chars[end] ?? '')

  return (
    (Number(oneCharBeforePause) + Number(oneCharAfterPause)) * SINGLE_CHARACTER_FRAGMENT_PENALTY
  )
}

/**
 * 首页竖排按列断句：优先整句和接近列底的标点，找不到合适句读才在字间断列。
 * 返回 null 表示当前高度/宽度不足，不强行制造只有两三字的短列。
 */
export function arrangeHomeColumns(
  text: string,
  capacity: number,
  maxColumns: number,
  options: { minInkLength?: number } = {},
): string[] | null {
  const chars = Array.from(text)
  if (!chars.length || capacity < 5 || maxColumns < 1) return null

  // dp[columnCount][characterOffset] 保存指定列数排到该字符时的最小代价。
  const dp: Array<Map<number, { cost: number; prev: number }>> = [
    new Map([[0, { cost: 0, prev: -1 }]]),
  ]
  for (let column = 1; column <= maxColumns; column++) {
    const states = new Map<number, { cost: number; prev: number }>()
    for (const [start, state] of dp[column - 1]) {
      for (let end = start + 1; end <= Math.min(chars.length, start + capacity); end++) {
        const part = chars.slice(start, end).join('')
        const contentLength = hanCount(part)
        // 重叠句等四字短句可以例外，优于把一个完整语气单位硬拆开。
        if (contentLength < 4 && !(start === 0 && end === chars.length)) continue
        if (end < chars.length && CLOSING_MARK.test(chars[end])) continue

        const endMark = chars[end - 1]
        const isLast = end === chars.length
        const unused = capacity - (end - start)
        const punctuationPenalty = isLast
          ? 0
          : SENTENCE_END.test(endMark)
            ? 0
            : CLAUSE_END.test(endMark)
              ? 3
              : 40
        const shortPenalty = unused * unused * (isLast ? 0.2 : 0.45)
        // 当片间全角空格正好遇到断列，允许把留白省去：不要让新列以空格开头。
        const cost =
          state.cost +
          punctuationPenalty +
          shortPenalty +
          danglingCharacterPenalty(chars, start, end) +
          2 +
          (contentLength === 4 ? 9 : 0)
        const previous = states.get(end)
        if (!previous || previous.cost > cost) states.set(end, { cost, prev: start })
      }
    }
    dp.push(states)
  }

  const reconstruct = (count: number): string[] | null => {
    const columns: string[] = []
    let offset = chars.length
    for (let row = count; row > 0; row--) {
      const previous = dp[row].get(offset)
      if (!previous) return null
      // 分片恰好从新行开始时，去掉装饰用的全角空格。
      columns.unshift(
        chars
          .slice(previous.prev, offset)
          .join('')
          .replace(/^\u3000/u, ''),
      )
      offset = previous.prev
    }
    return columns
  }

  let best: string[] | null = null
  let bestCost = Infinity
  for (let count = 1; count < dp.length; count++) {
    const final = dp[count].get(chars.length)
    if (!final) continue
    const candidate = reconstruct(count)
    if (!candidate) continue

    // 视觉高度不计行尾标点；不可把只有标点的尾格当作正文长度。
    const inkLength = Math.max(...candidate.map(inkCharacterCount))
    if (options.minInkLength && inkLength < options.minInkLength) continue

    if (final.cost < bestCost) {
      best = candidate
      bestCost = final.cost
    }
  }
  return best
}

function hanCount(text: string) {
  return Array.from(text).filter((char) => !/[\p{P}\s]/u.test(char)).length
}

/** 只计入正文真正留下的字格，行末标点及紧随的闭合符号不算高度。 */
export function inkCharacterCount(line: string): number {
  const suffix = /[，。！？,.!?;:；：、]+[”’」』））》】]*$/u
  return Array.from(line.replace(suffix, '').trimEnd()).length
}
