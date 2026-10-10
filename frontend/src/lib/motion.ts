/**
 * Read one timing token shared by CSS transitions and JavaScript sequencing.
 * Missing/invalid values fall back to zero so a switch never gets stuck.
 */
export function motionDurationMs(token: string): number {
  const value = getComputedStyle(document.documentElement).getPropertyValue(token).trim()
  const duration = Number.parseFloat(value)
  if (!Number.isFinite(duration) || duration < 0) return 0
  if (value.endsWith('ms')) return duration
  if (value.endsWith('s')) return duration * 1000
  return 0
}
