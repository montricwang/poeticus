import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { ClerkProvider } from '@clerk/react'
import { zhCN } from '@clerk/localizations/zh-CN'
import { clerkPublishableKey } from './lib/clerk-config.ts'
import App from './App.tsx'
import { ClerkBoundApp } from './components/clerk-bound-app.tsx'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {clerkPublishableKey ? (
      <ClerkProvider publishableKey={clerkPublishableKey} localization={zhCN}>
        <ClerkBoundApp />
      </ClerkProvider>
    ) : (
      <App />
    )}
  </StrictMode>,
)
