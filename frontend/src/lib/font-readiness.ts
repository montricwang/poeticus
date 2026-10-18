/**
 * 等字体排版稳定后入场；字体下载迟滞时也不能让页面一直保持透明。
 * 返回清理函数，供 React Effect 卸载时取消尚未触发的回调。
 */
export function whenFontsReadyOrTimeout(onReady: () => void, timeoutMs = 100): () => void {
  let active = true
  let completed = false
  const reveal = () => {
    if (!active || completed) return
    completed = true
    window.clearTimeout(deadline)
    onReady()
  }
  const deadline = window.setTimeout(reveal, timeoutMs)
  void document.fonts.ready.then(reveal, reveal)
  return () => {
    active = false
    window.clearTimeout(deadline)
  }
}
