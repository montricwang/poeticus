import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'

import { buildPoemLines, buildPoemTextRuns } from '@/lib/poem-layout'
import { selectionFromPoemRange } from '@/lib/poem-dom-selection'
import type { SelectedText } from '@/types/poem'

/**
 * 正文组件的数据接口：
 * poem：规范原文；修改显示方式时不能向它插入排版字符。
 * selectionScopeRef：整个阅读区，维持从题头拖动到正文的原有交互。
 * onSelect：把所选原文和 UTF-16 [start, end) 偏移交给上层提问组件。
 */
type PoemBodyProps = {
  poem: string
  selectionScopeRef: RefObject<HTMLDivElement | null>
  onSelect: (selection: SelectedText) => void
}

/** 只管理正文显示、划词、复制；题目、小序和网络读取由上层负责。 */
export function PoemBody({ poem, selectionScopeRef, onSelect }: PoemBodyProps) {
  // 防止标题/小序进入正文的原文偏移计算。
  const poemRef = useRef<HTMLParagraphElement>(null)
  // 视觉分行从原文派生，不修改传给 AI 的 poem。
  const lines = buildPoemLines(poem)

  useEffect(() => {
    // 记录是否仍在拖动，避免中途的 selectionchange 反复提交选区。
    let pointerDown = false
    let pointerStartedInReader = false

    /**
     * 浏览器的选区不等于原文字符串位置；先换算并校验，再通知 onSelect。
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

      // Keep the existing reader-wide pointer anchor, allowing drags to clip
      // at the body boundary without treating headings or prefaces as verse.
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
      // Do not change native copy when the selection also includes a heading or preface.
      if (!element.contains(range.startContainer) || !element.contains(range.endContainer)) {
        return
      }

      const selected = selectionFromPoemRange(element, range, poem)
      if (!selected || !event.clipboardData) return
      // Visual block lines can insert synthetic newlines in the browser's clipboard.
      event.clipboardData.setData('text/plain', selected.text)
      event.preventDefault()
    }

    /** 只记录拖选起点是否在阅读区，不在按下时立即引用。 */
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

    // 原来是 document 级监听；切换作品时要在清理函数中逐项注销。
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
      {/* display:block 只改变视觉行序；后代 DOM 文本依次拼接仍是完整原文。 */}
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
