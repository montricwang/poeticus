import { useEffect, useState } from 'react'
import { SignInButton, UserButton, useAuth } from '@clerk/react'

import { Button } from '@/components/ui/button'
import { clerkPublishableKey } from '@/lib/clerk-config'

/** Keep the public site usable when Clerk is not configured. */
export function AuthControls() {
  if (!clerkPublishableKey) return null
  return <ConfiguredAuthControls />
}

function ConfiguredAuthControls() {
  const { isLoaded, isSignedIn, userId, getToken } = useAuth()
  const [checked, setChecked] = useState<{ userId: string; valid: boolean } | null>(null)

  // The browser's signed-in state is not a backend authorization decision.
  // Verify it against FastAPI; never place the token in URL or localStorage.
  useEffect(() => {
    if (!isLoaded || !isSignedIn || !userId) return

    let active = true
    const currentUserId = userId
    async function checkBackend() {
      try {
        const token = await getToken()
        if (!token) throw new Error('Missing session token')
        const response = await fetch('/api/auth/me', {
          method: 'GET',
          headers: { Authorization: `Bearer ${token}` },
          cache: 'no-store',
        })
        if (!response.ok) throw new Error('Backend verification failed')
        const body: unknown = await response.json()
        const valid =
          typeof body === 'object' &&
          body !== null &&
          'clerk_user_id' in body &&
          body.clerk_user_id === currentUserId
        if (!valid) throw new Error('Unexpected verified user')
        if (active) setChecked({ userId: currentUserId, valid: true })
      } catch {
        if (active) setChecked({ userId: currentUserId, valid: false })
      }
    }
    void checkBackend()
    return () => {
      active = false
    }
  }, [getToken, isLoaded, isSignedIn, userId])

  if (!isLoaded) return null

  if (!isSignedIn) {
    return (
      <SignInButton mode="modal">
        <Button type="button" variant="ghost" size="sm">
          登录
        </Button>
      </SignInButton>
    )
  }

  const checkFailed = checked?.userId === userId && !checked.valid
  return (
    <div className="flex items-center gap-2">
      {checkFailed && (
        <span
          className="text-[11px] text-destructive"
          role="status"
          title="Clerk 已登录，但 Poeticus 服务器尚未确认身份；请检查后端 Clerk 配置"
        >
          身份未验证
        </span>
      )}
      <UserButton />
    </div>
  )
}
