import type { SelectedText } from '@/types/poem'

/** 浏览器的字符串位置以 UTF-16 单位计；Python 用 Unicode code point。 */
export function selectionForPython(
  selection: SelectedText | null,
  poem: string,
): SelectedText | null {
  if (!selection) return null
  if (
    selection.start < 0 ||
    selection.start >= selection.end ||
    selection.end > poem.length ||
    poem.slice(selection.start, selection.end) !== selection.text
  ) {
    return null
  }
  return {
    text: selection.text,
    start: Array.from(poem.slice(0, selection.start)).length,
    end: Array.from(poem.slice(0, selection.end)).length,
  }
}

export function validSelectionForPoem(
  selection: SelectedText | null,
  poem: string,
): SelectedText | null {
  if (!selection) return null

  if (
    selection.start < 0 ||
    selection.end > poem.length ||
    selection.start >= selection.end ||
    poem.slice(selection.start, selection.end) !== selection.text
  ) {
    return null
  }

  return selection
}
