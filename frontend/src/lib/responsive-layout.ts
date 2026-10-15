// 阅读/讨论模式边界与 Tailwind 的 lg 断点保持一致。
// 这些宽度决定交互方式，JavaScript 判断与 CSS 媒体查询必须同步。
export const WIDE_DISCUSSION_MIN_WIDTH = 1024
export const WIDE_DISCUSSION_MEDIA = `(min-width: ${WIDE_DISCUSSION_MIN_WIDTH}px)`
export const OVERLAY_CATALOG_MEDIA = `(max-width: ${WIDE_DISCUSSION_MIN_WIDTH - 1}px)`
