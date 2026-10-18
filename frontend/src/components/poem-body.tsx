import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { CSSProperties, RefObject } from 'react'

import { buildPoemLines, buildPoemTextRuns } from '@/lib/poem-layout'
import { selectionFromPoemRange } from '@/lib/poem-dom-selection'
import {
  adaptiveOpticalStrength,
  inkTextLength,
  opticalCenterOffset,
} from '@/lib/poem-optical-center'
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
  selected: SelectedText | null
}

/**
 * 测量行内前 length 个 UTF-16 字符占据的实际宽度。
 * 一行可以包含多个文字、标点 span，因此遍历文本节点建立 Range。
 */
function textPrefixRect(line: HTMLElement, length: number): DOMRect | null {
  if (length <= 0) return null
  const walker = document.createTreeWalker(line, NodeFilter.SHOW_TEXT)
  const first = walker.nextNode()
  if (!first) return null

  const range = document.createRange()
  range.setStart(first, 0)
  let remaining = length
  let node: Node | null = first

  while (node) {
    const nodeLength = node.textContent?.length ?? 0
    if (remaining <= nodeLength) {
      range.setEnd(node, remaining)
      const rect = range.getBoundingClientRect()
      return rect.width > 0 ? rect : null
    }
    remaining -= nodeLength
    node = walker.nextNode()
  }
  return null
}

type QuoteUnderline = { left: number; top: number; width: number }

/**
 * 对引用范围内的每个叶子文本节点分别取几何信息。
 * 对跨父子节点创建的整段 Range 调用 getClientRects() 会把块级行盒、
 * 标点 span 和文字矩形一起返回，同一行就会出现重复或超长标线。
 * 保留 UTF-16 偏移对应关系，不拆分原文 DOM，也不依赖浏览器选区。
 */
function quoteTextRects(
  root: HTMLElement,
  start: number,
  end: number,
): { rect: DOMRect; line: Element }[] {
  const fragments: { rect: DOMRect; line: Element }[] = []
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  let cursor = 0

  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node as Text
    const length = text.data.length
    const from = Math.max(0, start - cursor)
    const to = Math.min(length, end - cursor)

    if (to > from) {
      const line = text.parentElement?.closest('.poem-reader-line')
      if (line) {
        const range = document.createRange()
        range.setStart(text, from)
        range.setEnd(text, to)
        for (const rect of range.getClientRects()) {
          if (rect.width > 0.5 && rect.height > 0.5) fragments.push({ rect, line })
        }
      }
    }

    cursor += length
    if (cursor >= end) break
  }
  return fragments
}

/** 负责诗文正文的排版、选区引用和复制交互。 */
export function PoemBody({ poem, selectionScopeRef, onSelect, selected }: PoemBodyProps) {
  // 正文容器定义选区偏移的计算范围。
  const poemRef = useRef<HTMLParagraphElement>(null)
  const [quoteUnderlines, setQuoteUnderlines] = useState<QuoteUnderline[]>([])

  useLayoutEffect(() => {
    const block = poemRef.current
    if (
      !block ||
      !selected ||
      selected.start >= selected.end ||
      poem.slice(selected.start, selected.end) !== selected.text
    ) {
      setQuoteUnderlines([])
      return
    }

    function measure() {
      if (!block || block.textContent !== poem) return
      const fragments = quoteTextRects(block, selected!.start, selected!.end)
      const rows: { line: Element; left: number; right: number; top: number; bottom: number }[] = []

      for (const { rect, line } of fragments) {
        // 必须属于同一个诗行，且字形盒子在纵向上确实重叠，才算同一显示行；
        // 不再按 bottom 相差 3px 猜测，也不会把整块的行盒误当成文字宽度。
        const row = rows.find((item) => {
          if (item.line !== line) return false
          const overlap = Math.min(item.bottom, rect.bottom) - Math.max(item.top, rect.top)
          return overlap > Math.min(item.bottom - item.top, rect.height) / 2
        })
        if (row) {
          row.left = Math.min(row.left, rect.left)
          row.right = Math.max(row.right, rect.right)
          row.top = Math.min(row.top, rect.top)
          row.bottom = Math.max(row.bottom, rect.bottom)
        } else {
          rows.push({
            line,
            left: rect.left,
            right: rect.right,
            top: rect.top,
            bottom: rect.bottom,
          })
        }
      }

      const origin = block.getBoundingClientRect()
      setQuoteUnderlines(
        rows.map((row) => ({
          left: row.left - origin.left,
          top: row.bottom - origin.top + 1,
          width: row.right - row.left,
        })),
      )
    }

    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(block)
    if (block.parentElement) observer.observe(block.parentElement)
    let active = true
    void document.fonts.ready.then(() => {
      if (active) measure()
    })
    return () => {
      active = false
      observer.disconnect()
    }
  }, [poem, selected])

  // 根据原文生成用于展示的诗行。
  const lines = buildPoemLines(poem)

  useLayoutEffect(() => {
    // 开发环境可临时使用 classic 对照原布局；默认启用动态质心居中。
    const mode = import.meta.env.DEV
      ? new URLSearchParams(window.location.search).get('poemCenter')
      : null
    if (mode === 'classic') return

    const block = poemRef.current
    const container = block?.parentElement
    if (!block || !container) return

    function update() {
      if (!block || !container) return
      const blockRect = block.getBoundingClientRect()
      const containerStyle = getComputedStyle(container)
      const availableWidth =
        container.clientWidth -
        Number.parseFloat(containerStyle.paddingLeft) -
        Number.parseFloat(containerStyle.paddingRight)

      const measures = []
      for (const line of block.querySelectorAll<HTMLElement>('.poem-reader-line')) {
        // 诗句自然折行时退回普通居中，不拿折行后的矩形计算单行重心。
        const lineHeight = Number.parseFloat(getComputedStyle(line).lineHeight)
        if (Number.isFinite(lineHeight) && line.getBoundingClientRect().height > lineHeight * 1.5) {
          block.style.translate = ''
          return
        }

        const inkRect = textPrefixRect(line, inkTextLength(line.textContent ?? ''))
        if (!inkRect) continue
        const start = inkRect.left - blockRect.left
        if (start < -0.5 || start + inkRect.width > blockRect.width + 0.5) {
          block.style.translate = ''
          return
        }
        measures.push({ start: Math.max(0, start), width: inkRect.width })
      }

      const strength = adaptiveOpticalStrength(measures)
      const offset = opticalCenterOffset(measures, blockRect.width, availableWidth, strength)
      block.style.translate = Math.abs(offset) < 0.5 ? '' : `${offset.toFixed(2)}px 0`
    }

    const observer = new ResizeObserver(update)
    observer.observe(container)
    observer.observe(block)
    update()

    // 字体异步加载和字体回退都可能改变文字的真实宽度。
    let active = true
    void document.fonts.ready.then(() => {
      if (active) update()
    })
    return () => {
      active = false
      observer.disconnect()
      block.style.translate = ''
    }
  }, [poem])

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
      className="poem-reader-body relative mx-auto w-fit max-w-full cursor-text select-text whitespace-normal font-serif text-foreground/90"
    >
      {/* 各诗行及标点节点的文本按 DOM 顺序拼接，应等于完整原文。 */}
      {lines.map((line, index) => (
        <span
          key={line.start}
          style={{ '--reader-stagger-index': Math.min(index, 9) } as CSSProperties}
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
      {selected &&
        quoteUnderlines.map((line, index) => (
          <span
            key={selected.start + '-' + selected.end + '-' + index}
            aria-hidden="true"
            className="poem-quote-underline"
            style={{ left: line.left, top: line.top, width: line.width }}
          />
        ))}
    </p>
  )
}
