import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'

import type { SelectedText } from '@/types/poem'

type PoemBodyProps = {
  poem: string
  selectionScopeRef: RefObject<HTMLDivElement | null>
  onSelect: (selection: SelectedText) => void
}

/**
 * 正文的展示与选区归属边界。当前先保持单文本节点及原有 DOM 选区行为；
 * 后续拆分标点与诗行时，必须先替换 source-offset 映射并验证引用准确性。
 */
export function PoemBody({ poem, selectionScopeRef, onSelect }: PoemBodyProps) {
  const poemRef = useRef<HTMLParagraphElement>(null)

  useEffect(() => {
    let pointerDown = false
    let pointerStartedInReader = false

    function handleSelection(allowOutsideAnchor = false) {
      const reader = selectionScopeRef.current
      const element = poemRef.current
      const selection = window.getSelection()

      if (
        !reader ||
        !element ||
        !selection ||
        selection.isCollapsed ||
        selection.rangeCount === 0
      ) {
        return
      }

      // 键盘选择等情况，仍要求从左侧阅读区域开始。
      // 鼠标操作则使用 pointerdown 记录的起点判断。
      if (
        !allowOutsideAnchor &&
        (!selection.anchorNode || !reader.contains(selection.anchorNode))
      ) {
        return
      }

      // 正文保留为一个文本节点，标题与词序不参与 offset 计算。
      const textNode = element.firstChild
      if (!textNode || textNode.nodeType !== Node.TEXT_NODE) {
        return
      }

      const range = selection.getRangeAt(0)
      const poemRange = document.createRange()
      poemRange.selectNodeContents(textNode)

      const endsBeforePoem = range.compareBoundaryPoints(Range.START_TO_END, poemRange) <= 0
      const startsAfterPoem = range.compareBoundaryPoints(Range.END_TO_START, poemRange) >= 0
      if (endsBeforePoem || startsAfterPoem) {
        return
      }

      const clippedRange = range.cloneRange()
      if (clippedRange.compareBoundaryPoints(Range.START_TO_START, poemRange) < 0) {
        clippedRange.setStart(textNode, 0)
      }
      if (clippedRange.compareBoundaryPoints(Range.END_TO_END, poemRange) > 0) {
        clippedRange.setEnd(textNode, textNode.textContent?.length ?? 0)
      }

      const text = clippedRange.toString()
      if (!text.trim()) {
        return
      }

      const prefixRange = document.createRange()
      prefixRange.selectNodeContents(textNode)
      prefixRange.setEnd(clippedRange.startContainer, clippedRange.startOffset)

      const start = prefixRange.toString().length
      const end = start + text.length
      if (poem.slice(start, end) !== text) {
        return
      }
      onSelect({ text, start, end })
    }

    function handlePointerDown(event: PointerEvent) {
      pointerDown = true
      pointerStartedInReader =
        event.target instanceof Node && !!selectionScopeRef.current?.contains(event.target)
    }

    function handlePointerUp() {
      const startedInReader = pointerStartedInReader
      pointerDown = false
      pointerStartedInReader = false
      if (startedInReader) {
        handleSelection(true)
      }
    }

    function handlePointerCancel() {
      pointerDown = false
      pointerStartedInReader = false
    }

    function handleSelectionChange() {
      if (!pointerDown) {
        handleSelection()
      }
    }

    document.addEventListener('pointerdown', handlePointerDown, true)
    window.addEventListener('pointerup', handlePointerUp)
    window.addEventListener('pointercancel', handlePointerCancel)
    document.addEventListener('selectionchange', handleSelectionChange)

    return () => {
      document.removeEventListener('pointerdown', handlePointerDown, true)
      window.removeEventListener('pointerup', handlePointerUp)
      window.removeEventListener('pointercancel', handlePointerCancel)
      document.removeEventListener('selectionchange', handleSelectionChange)
    }
  }, [onSelect, poem])

  return (
    <p
      ref={poemRef}
      className="poem-reader-body mx-auto w-fit max-w-full cursor-text select-text whitespace-pre-line font-serif text-foreground/90 selection:bg-violet-200 selection:text-violet-950 dark:selection:bg-violet-400/40 dark:selection:text-white"
    >
      {poem}
    </p>
  )
}
