import { useAuth } from '@clerk/react'

import App from '@/App'

/** Remount when changing accounts; browser-local chat caches are user-scoped. */
export function ClerkBoundApp() {
  const { isLoaded, userId, getToken } = useAuth()
  if (!isLoaded) return null
  return <App key={userId ?? 'guest'} accountId={userId} getAuthToken={getToken} />
}
