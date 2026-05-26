import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MsalProvider } from '@azure/msal-react'
import { msalInstance } from './lib/auth'
import './index.css'
import App from './App.tsx'

async function startApp() {
  try {
    await msalInstance.initialize()
    await msalInstance.handleRedirectPromise()
  } catch (e) {
    console.error('MSAL init error:', e)
  }

  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <MsalProvider instance={msalInstance}>
        <App />
      </MsalProvider>
    </StrictMode>,
  )
}

startApp()
