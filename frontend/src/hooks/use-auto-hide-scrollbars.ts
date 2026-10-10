import { useEffect } from 'react'

/**
 * Reveal the native thumb only while a scrollport is scrolling.
 * A single capturing listener covers reader, chat, analysis, catalog, quotes,
 * textareas and nested Markdown without a separate handler in every component.
 * We never change scrollbar width, scrollbar-color or overflow properties.
 */
export function useAutoHideScrollbars() {
  useEffect(() => {
    const pending = new Map<HTMLElement, number>()

    function onScroll(event: Event) {
      const element = event.target
      if (!(element instanceof HTMLElement) || !element.classList.contains('poeticus-scrollport')) {
        return
      }

      element.dataset.scrolling = 'true'
      const previous = pending.get(element)
      if (previous !== undefined) window.clearTimeout(previous)
      pending.set(
        element,
        window.setTimeout(() => {
          element.removeAttribute('data-scrolling')
          pending.delete(element)
        }, 900),
      )
    }

    // scroll doesn't bubble; capture the event at the document boundary.
    document.addEventListener('scroll', onScroll, true)
    return () => {
      document.removeEventListener('scroll', onScroll, true)
      for (const [element, timer] of pending) {
        window.clearTimeout(timer)
        element.removeAttribute('data-scrolling')
      }
      pending.clear()
    }
  }, [])
}
