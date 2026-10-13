/**
 * 读取 CSS 动画与 JavaScript 执行顺序共用的时长变量。
 * 缺失或无效时返回零，避免界面切换一直等待。
 */
export function motionDurationMs(token: string): number {
  const value = getComputedStyle(document.documentElement).getPropertyValue(token).trim()
  const duration = Number.parseFloat(value)
  if (!Number.isFinite(duration) || duration < 0) return 0
  if (value.endsWith('ms')) return duration
  if (value.endsWith('s')) return duration * 1000
  return 0
}
