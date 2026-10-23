import { useEffect, useState } from 'react'
import { SignInButton, SignUpButton, UserButton, useAuth } from '@clerk/react'

import { Button } from '@/components/ui/button'
import { clerkPublishableKey } from '@/lib/clerk-config'

type VerifiedSession = {
  userId: string
  valid: boolean
  memoryOptIn: boolean
  memoryAvailable: boolean
}
type UserMemory = {
  id: string
  memory: string
  source?: string
  conversation_id?: string | null
  source_message_id?: string | null
  original_conversation_id?: string | null
  original_source_message_id?: string | null
}

/** Keep public reading and chat available without Clerk configuration. */
export function AuthControls() {
  if (!clerkPublishableKey) return null
  return <ConfiguredAuthControls />
}

function ConfiguredAuthControls() {
  const { isLoaded, isSignedIn, userId, getToken } = useAuth()
  const [session, setSession] = useState<VerifiedSession | null>(null)
  const [memories, setMemories] = useState<UserMemory[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [sourcePreview, setSourcePreview] = useState<{ id: string; content: string } | null>(null)
  const [editText, setEditText] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (!isLoaded || !isSignedIn || !userId) return

    let active = true
    const currentUserId = userId
    async function verify() {
      try {
        const token = await getToken()
        if (!token) throw new Error('No session token')
        const response = await fetch('/api/auth/session', {
          method: 'POST',
          headers: { Authorization: 'Bearer ' + token },
          cache: 'no-store',
        })
        if (!response.ok) throw new Error('Backend verification failed')
        const body: unknown = await response.json()
        const valid =
          typeof body === 'object' &&
          body !== null &&
          'clerk_user_id' in body &&
          body.clerk_user_id === currentUserId &&
          'user_id' in body &&
          typeof body.user_id === 'string' &&
          body.user_id.length > 0
        if (!valid) throw new Error('Unexpected verified identity')
        if (active) {
          setSession({
            userId: currentUserId,
            valid: true,
            memoryOptIn: 'memory_opt_in' in body && body.memory_opt_in === true,
            memoryAvailable: 'memory_available' in body && body.memory_available === true,
          })
        }
      } catch {
        if (active) {
          setSession({
            userId: currentUserId,
            valid: false,
            memoryOptIn: false,
            memoryAvailable: false,
          })
        }
      }
    }
    void verify()
    return () => {
      active = false
    }
  }, [getToken, isLoaded, isSignedIn, userId])

  async function authorizedFetch(path: string, method: string, body?: object) {
    const token = await getToken()
    if (!token) throw new Error('登录凭证已失效')
    const response = await fetch(path, {
      method,
      headers: {
        Authorization: 'Bearer ' + token,
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      cache: 'no-store',
    })
    if (!response.ok) throw new Error('请求失败，请检查服务并重试')
    return response
  }

  async function changeMemory(enabled: boolean) {
    if (!session?.valid || busy) return
    if (
      enabled &&
      !window.confirm(
        '开启后，Poeticus 会从你接下来的讨论中提炼阅读偏好，并保存在私人记忆中。你可以随时关闭或清除。是否开启？',
      )
    )
      return
    setBusy(true)
    setError('')
    try {
      const response = await authorizedFetch('/api/auth/memory-preference', 'PUT', {
        enabled,
      })
      const body: { memory_opt_in: boolean } = await response.json()
      setSession((previous) => previous && { ...previous, memoryOptIn: body.memory_opt_in })
    } catch {
      setError('记忆设置未保存')
    } finally {
      setBusy(false)
    }
  }

  async function viewMemories() {
    setBusy(true)
    setError('')
    try {
      const response = await authorizedFetch('/api/memories', 'GET')
      const body: { memories: UserMemory[] } = await response.json()
      setMemories(body.memories)
    } catch {
      setError('无法读取记忆，请检查服务')
    } finally {
      setBusy(false)
    }
  }

  async function clearMemories() {
    if (!window.confirm('确定删除所有长期记忆并关闭记忆提取吗？对话记录不会因此删除。')) return
    setBusy(true)
    setError('')
    try {
      const response = await authorizedFetch('/api/memories', 'DELETE')
      const result: { memory_opt_in: boolean } = await response.json()
      setMemories([])
      setSession((previous) => previous && { ...previous, memoryOptIn: result.memory_opt_in })
      setEditingId(null)
    } catch {
      setError('记忆未能全部删除，请重试')
    } finally {
      setBusy(false)
    }
  }

  async function saveCorrection(memoryId: string) {
    const nextText = editText.trim()
    if (!nextText || nextText.length > 300 || busy) return
    setBusy(true)
    setError('')
    try {
      const response = await authorizedFetch(
        '/api/memories/' + encodeURIComponent(memoryId),
        'PATCH',
        { text: nextText },
      )
      const corrected: UserMemory = await response.json()
      setMemories(
        (previous) => previous?.map((item) => (item.id === memoryId ? corrected : item)) ?? null,
      )
      setEditingId(null)
    } catch {
      setError('记忆更正失败，请重试')
    } finally {
      setBusy(false)
    }
  }

  async function viewSource(memory: UserMemory) {
    const conversationId = memory.conversation_id ?? memory.original_conversation_id
    const sourceMessageId = memory.source_message_id ?? memory.original_source_message_id
    if (!conversationId || !sourceMessageId) return
    setBusy(true)
    setError('')
    try {
      const response = await authorizedFetch(
        '/api/conversations/' + encodeURIComponent(conversationId),
        'GET',
      )
      const data: { messages: { id: string; content: string }[] } = await response.json()
      const original = data.messages.find((message) => message.id === sourceMessageId)
      setSourcePreview({
        id: memory.id,
        content: original?.content ?? '来源消息已不存在',
      })
    } catch {
      setError('无法查阅来源讨论')
    } finally {
      setBusy(false)
    }
  }

  async function deleteOne(memoryId: string) {
    if (!window.confirm('删除这条私人记忆？')) return
    setBusy(true)
    setError('')
    try {
      await authorizedFetch('/api/memories/' + encodeURIComponent(memoryId), 'DELETE')
      setMemories((previous) => previous?.filter((item) => item.id !== memoryId) ?? null)
      setEditingId(null)
    } catch {
      setError('单条记忆删除失败')
    } finally {
      setBusy(false)
    }
  }

  if (!isLoaded) return null
  if (!isSignedIn) {
    return (
      <div className="flex items-center gap-0.5">
        <SignInButton mode="modal">
          <Button type="button" variant="ghost" size="sm" className="px-2">
            登录
          </Button>
        </SignInButton>
        <SignUpButton mode="modal">
          <Button type="button" variant="ghost" size="sm" className="px-2">
            注册
          </Button>
        </SignUpButton>
      </div>
    )
  }

  const verified = session?.userId === userId && session.valid
  const checkFailed = session?.userId === userId && !session.valid
  return (
    <div className="flex items-center gap-2">
      {checkFailed && (
        <span className="text-[11px] text-destructive" role="status">
          身份未验证
        </span>
      )}
      {verified && (
        <details className="relative text-xs">
          <summary className="cursor-pointer list-none rounded px-2 py-1.5 text-muted-foreground hover:text-foreground">
            记忆
          </summary>
          <div className="absolute top-full right-0 z-50 mt-2 w-70 max-w-[90vw] rounded-md border border-border bg-background p-4 shadow-lg">
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={session.memoryOptIn}
                disabled={busy || (!session.memoryAvailable && !session.memoryOptIn)}
                onChange={(event) => void changeMemory(event.target.checked)}
              />
              开启私人长期记忆
            </label>
            {!session.memoryAvailable && (
              <p className="mt-2 text-muted-foreground">本地记忆服务尚未启用</p>
            )}
            <p className="mt-2 text-muted-foreground">
              关闭后不再读取或提炼记忆；已有记录需单独删除。
            </p>
            <div className="mt-3 flex items-center gap-3">
              <button
                type="button"
                className="underline"
                disabled={busy}
                onClick={() => void viewMemories()}
              >
                查看记忆
              </button>
              <button
                type="button"
                className="text-destructive underline"
                disabled={busy}
                onClick={() => void clearMemories()}
              >
                清除全部
              </button>
            </div>
            {memories && (
              <ul className="mt-3 max-h-40 list-disc space-y-2 overflow-y-auto pl-4">
                {memories.length === 0 ? (
                  <li>暂无记忆</li>
                ) : (
                  memories.map((item) => (
                    <li key={item.id} className="space-y-1">
                      {editingId === item.id ? (
                        <div className="space-y-1">
                          <textarea
                            aria-label="更正私人记忆"
                            className="w-full rounded border border-border bg-background p-1"
                            rows={3}
                            maxLength={300}
                            value={editText}
                            onChange={(event) => setEditText(event.target.value)}
                          />
                          <div className="flex gap-3">
                            <button
                              type="button"
                              className="underline"
                              disabled={busy || !editText.trim()}
                              onClick={() => void saveCorrection(item.id)}
                            >
                              保存更正
                            </button>
                            <button
                              type="button"
                              className="underline"
                              onClick={() => setEditingId(null)}
                            >
                              取消
                            </button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <p>{item.memory}</p>
                          <p className="text-muted-foreground">
                            {item.source === 'user_correction' ? '本人修订' : '来自阅读讨论'}
                          </p>
                          {((item.conversation_id && item.source_message_id) ||
                            (item.original_conversation_id && item.original_source_message_id)) && (
                            <button
                              type="button"
                              className="underline"
                              disabled={busy}
                              onClick={() => void viewSource(item)}
                            >
                              {item.source === 'user_correction' ? '查看更正前来源' : '查看来源'}
                            </button>
                          )}
                          {sourcePreview?.id === item.id && (
                            <p className="rounded bg-muted/40 p-2 text-foreground">
                              原始提问：{sourcePreview.content}
                            </p>
                          )}
                          <div className="flex gap-3">
                            <button
                              type="button"
                              disabled={busy}
                              className="underline"
                              onClick={() => {
                                setEditingId(item.id)
                                setEditText(item.memory)
                              }}
                            >
                              更正
                            </button>
                            <button
                              type="button"
                              disabled={busy}
                              className="text-destructive underline"
                              onClick={() => void deleteOne(item.id)}
                            >
                              删除
                            </button>
                          </div>
                        </>
                      )}
                    </li>
                  ))
                )}
              </ul>
            )}
            {error && (
              <p className="mt-2 text-destructive" role="alert">
                {error}
              </p>
            )}
          </div>
        </details>
      )}
      <UserButton />
    </div>
  )
}
