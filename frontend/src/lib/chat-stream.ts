/** 正常的额度限制不是生成故障，前端应以中性提示呈现。 */
export class UsageLimitNotice extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'UsageLimitNotice'
  }
}

/** 读取 POST /chat/stream 的 SSE。HTTP 数据块边界不等于 SSE 事件边界。 */
export async function readChatStream(
  response: Response,
  onToken: (text: string) => void,
): Promise<void> {
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    const detail =
      typeof body === 'object' && body !== null && 'detail' in body ? body.detail : null
    const message = typeof detail === 'string' ? detail : `请求失败：HTTP ${response.status}`
    throw response.status === 429 ? new UsageLimitNotice(message) : new Error(message)
  }

  if (!response.headers.get('content-type')?.includes('text/event-stream')) {
    throw new Error('服务器未返回流式响应，请确认已启动新版后端')
  }
  if (!response.body) {
    throw new Error('浏览器无法读取流式响应')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let completed = false

  function processEvent(block: string): void {
    let event = 'message'
    const data: string[] = []
    for (const line of block.split('\n')) {
      if (!line || line.startsWith(':')) continue
      const separator = line.indexOf(':')
      const field = separator < 0 ? line : line.slice(0, separator)
      const raw = separator < 0 ? '' : line.slice(separator + 1)
      const value = raw.startsWith(' ') ? raw.slice(1) : raw
      if (field === 'event') event = value
      if (field === 'data') data.push(value)
    }

    if (event !== 'token' && event !== 'done' && event !== 'error') {
      return
    }

    let payload: unknown
    try {
      payload = JSON.parse(data.join('\n'))
    } catch {
      throw new Error('服务器返回了无效的流式事件')
    }
    if (typeof payload !== 'object' || payload === null) {
      throw new Error('服务器返回了无效的流式事件')
    }

    if (event === 'token') {
      if (!('text' in payload) || typeof payload.text !== 'string') {
        throw new Error('流式事件缺少文本内容')
      }
      onToken(payload.text)
    } else if (event === 'error') {
      const message = 'message' in payload ? payload.message : null
      throw new Error(typeof message === 'string' ? message : 'AI 生成失败')
    } else {
      completed = true
    }
  }

  try {
    while (!completed) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      // SSE 允许 CRLF，且一条 JSON 事件可能跨多个 HTTP 数据块。
      buffer = buffer.replace(/\r\n/g, '\n')

      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        const block = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        processEvent(block)
        if (completed) break
        boundary = buffer.indexOf('\n\n')
      }
    }
    if (!completed) {
      throw new Error('连接提前中断，回答未完成')
    }
  } finally {
    if (completed) await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
}
