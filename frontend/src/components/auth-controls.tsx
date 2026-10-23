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
type UserMemory = { id: string; memory: string }

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
    if (!window.confirm('确定删除你的所有长期记忆吗？对话记录不会因此删除。')) return
    setBusy(true)
    setError('')
    try {
      await authorizedFetch('/api/memories', 'DELETE')
      setMemories([])
    } catch {
      setError('记忆未能全部删除，请重试')
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
                  memories.map((item) => <li key={item.id}>{item.memory}</li>)
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
