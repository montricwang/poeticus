import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'

import { buildPoemLines, buildPoemTextRuns } from '@/lib/poem-layout'
import { selectionFromPoemRange } from '@/lib/poem-dom-selection'
import type { SelectedText } from '@/types/poem'

type PoemBodyProps = {
  poem: string
  selectionScopeRef: RefObject<HTMLDivElement | null>
  onSelect: (selection: SelectedText) => void
}

export function PoemBody({ poem, selectionScopeRef, onSelect }: PoemBodyProps) {
  const poemRef = useRef<HTMLParagraphElement>(null)
  const lines = buildPoemLines(poem)

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
