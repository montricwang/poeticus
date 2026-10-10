import { useCallback, useEffect, useRef } from 'react'

/**
 * Keep the native scrollbar available for dragging, but reveal its thumb only
 * after direct scroll input (wheel/touch; keyboard focus stays discoverable).
 * Programmatic scroll restoration must not flash the thumb on first paint.
 * Using a DOM attribute avoids rerendering long poem/chat/analysis content.
 */
export function useScrollActivity() {
  const timerRef = useRef<number | null>(null)
  const elementRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current)
      elementRef.current?.removeAttribute('data-scrolling')
    }
  }, [])

  return useCallback((element: HTMLElement) => {
    if (elementRef.current && elementRef.current !== element) {
      elementRef.current.removeAttribute('data-scrolling')
    }
    elementRef.current = element
    element.dataset.scrolling = 'true'

    if (timerRef.current !== null) window.clearTimeout(timerRef.current)
    timerRef.current = window.setTimeout(() => {
      element.removeAttribute('data-scrolling')
      timerRef.current = null
    }, 850)
  }, [])
}
