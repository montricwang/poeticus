export type ServiceCapabilities = {
  chat: {
    maxHistoryTurns: number
    maxQuestionChars: number
    maxSelectionChars: number
  }
}

// 共享一次服务能力请求；读取失败时清空缓存，允许下次重试。
let cached: Promise<ServiceCapabilities> | null = null

function positiveInteger(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isInteger(value) || value <= 0) {
    throw new Error(`服务能力字段无效：${field}`)
  }
  return value
}

async function fetchCapabilities(): Promise<ServiceCapabilities> {
  const response = await fetch('/api/capabilities', {
    headers: { Accept: 'application/json' },
  })

  if (!response.ok) {
    throw new Error('无法读取服务能力')
  }

  const payload = (await response.json()) as {
    chat?: {
      maxHistoryTurns?: unknown
      maxQuestionChars?: unknown
      maxSelectionChars?: unknown
    }
  }

  const chat = payload.chat
  if (!chat) {
    throw new Error('服务能力缺少聊天配置')
  }

  return {
    chat: {
      maxHistoryTurns: positiveInteger(chat.maxHistoryTurns, 'maxHistoryTurns'),
      maxQuestionChars: positiveInteger(chat.maxQuestionChars, 'maxQuestionChars'),
      maxSelectionChars: positiveInteger(chat.maxSelectionChars, 'maxSelectionChars'),
    },
  }
}

/** 读取后端发布的聊天参数上限，供前端构造请求和截断历史。 */
export function loadServiceCapabilities(): Promise<ServiceCapabilities> {
  if (!cached) {
    cached = fetchCapabilities().catch((error) => {
      cached = null
      throw error
    })
  }
  return cached
}
