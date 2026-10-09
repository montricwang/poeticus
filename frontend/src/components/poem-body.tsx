import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'

import { buildPoemLines, buildPoemTextRuns } from '@/lib/poem-layout'
import { selectionFromPoemRange } from '@/lib/poem-dom-selection'
import type { SelectedText } from '@/types/poem'

/**
 * 正文组件的数据接口：
 * poem：展示与引用共用的完整原文，字符顺序保持一致。
 * selectionScopeRef：整个阅读区，供拖选起点判断使用。
 * onSelect：把所选原文和 UTF-16 [start, end) 偏移交给上层提问组件。
 */
type PoemBodyProps = {
  poem: string
  selectionScopeRef: RefObject<HTMLDivElement | null>
  onSelect: (selection: SelectedText) => void
}

/** 负责诗文正文的排版、选区引用和复制交互。 */
export function PoemBody({ poem, selectionScopeRef, onSelect }: PoemBodyProps) {
  // 正文容器定义选区偏移的计算范围。
  const poemRef = useRef<HTMLParagraphElement>(null)
  // 根据原文生成用于展示的诗行。
  const lines = buildPoemLines(poem)

  useEffect(() => {
    // 拖选期间等待鼠标松开后再提交选区，避免重复提交中间状态。
    let pointerDown = false
    let pointerStartedInReader = false

    /**
     * 将浏览器选区映射到原文字符位置并通知 onSelect。
     * allowOutsideAnchor=true 仅用于已经从阅读区按下的鼠标拖选；
     * 键盘等方式仍要求选区锚点在阅读区。
     */
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

      // 鼠标拖选以阅读区为起点范围，实际引用的文字裁剪到正文。
      if (
        !allowOutsideAnchor &&
        (!selection.anchorNode || !reader.contains(selection.anchorNode))
      ) {
        return
      }

      const selected = selectionFromPoemRange(element, selection.getRangeAt(0), poem)
      if (selected) onSelect(selected)
    }

    /**
     * 块级诗行可能让浏览器在复制时额外插入换行。
     * 仅当选区完全处于正文时，用规范原文覆盖剪贴板纯文本；
     * 标题/小序混合选区仍交给浏览器处理。
     */
    function handleCopy(event: ClipboardEvent) {
      const element = poemRef.current
      const selection = window.getSelection()
      if (!element || !selection || selection.isCollapsed || selection.rangeCount === 0) {
        return
      }

      const range = selection.getRangeAt(0)
      // 选区包含标题或小序时，使用浏览器原生复制行为。
      if (!element.contains(range.startContainer) || !element.contains(range.endContainer)) {
        return
      }

      const selected = selectionFromPoemRange(element, range, poem)
      if (!selected || !event.clipboardData) return
      // 跨视觉诗行复制时，从原文提取连续文本，避免引入排版换行。
      event.clipboardData.setData('text/plain', selected.text)
      event.preventDefault()
    }

    /** 记录本次拖选是否从阅读区开始。 */
    function handlePointerDown(event: PointerEvent) {
      pointerDown = true
      pointerStartedInReader =
        event.target instanceof Node && !!selectionScopeRef.current?.contains(event.target)
    }

    /** 松开时读取最终选区，必要时裁剪到正文范围。 */
    function handlePointerUp() {
      const startedInReader = pointerStartedInReader
      pointerDown = false
      pointerStartedInReader = false
      if (startedInReader) {
        handleSelection(true)
      }
    }

    /** 手势取消时清空拖选状态，避免影响下一次选词。 */
    function handlePointerCancel() {
      pointerDown = false
      pointerStartedInReader = false
    }

    /** 响应键盘或系统原生手柄的选区变化；鼠标拖拽要等待松开。 */
    function handleSelectionChange() {
      if (!pointerDown) {
        handleSelection()
      }
    }

    // 全局监听器在 Effect 清理时逐项注销，避免切换作品后重复响应。
    document.addEventListener('pointerdown', handlePointerDown, true)
    window.addEventListener('pointerup', handlePointerUp)
    window.addEventListener('pointercancel', handlePointerCancel)
    document.addEventListener('selectionchange', handleSelectionChange)
    document.addEventListener('copy', handleCopy)

    return () => {
      document.removeEventListener('pointerdown', handlePointerDown, true)
      window.removeEventListener('pointerup', handlePointerUp)
      window.removeEventListener('pointercancel', handlePointerCancel)
      document.removeEventListener('selectionchange', handleSelectionChange)
      document.removeEventListener('copy', handleCopy)
    }
  }, [onSelect, poem, selectionScopeRef])

  return (
    <p
      ref={poemRef}
      className="poem-reader-body mx-auto w-fit max-w-full cursor-text select-text whitespace-normal font-serif text-foreground/90 selection:bg-violet-200 selection:text-violet-950 dark:selection:bg-violet-400/40 dark:selection:text-white"
    >
      {/* 各诗行及标点节点的文本按 DOM 顺序拼接，应等于完整原文。 */}
      {lines.map((line) => (
        <span
          key={line.start}
          className={'poem-reader-line' + (line.sourceGapBefore ? ' poem-reader-source-gap' : '')}
        >
          {buildPoemTextRuns(line.text).map((run, index) =>
            run.punctuation ? (
              <span className="poem-reader-punctuation" key={index}>
                {run.text}
              </span>
            ) : (
              <span key={index}>{run.text}</span>
            ),
          )}
        </span>
      ))}
    </p>
  )
}
