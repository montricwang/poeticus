import { useEffect } from 'react'

import { motionDurationMs } from '@/lib/motion'

/**
 * 仅在滚动时显示原生滚动条滑块。
 * 在 document 上使用一个捕获阶段监听器，统一处理阅读、聊天、赏析、目录、引用及输入区，
 * 不必让各组件分别监听；不改变滚动条宽度或容器的 overflow 设置。
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
        }, motionDurationMs('--motion-scrollbar-idle-timeout')),
      )
    }

    // scroll 事件不会冒泡，因此需要在 document 上通过捕获阶段监听。
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
