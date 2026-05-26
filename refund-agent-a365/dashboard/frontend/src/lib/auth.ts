/**
 * MSAL Configuration for Entra ID authentication
 * Replace the clientId and authority with your own Entra ID app registration values.
 */
import { PublicClientApplication, type Configuration } from '@azure/msal-browser'

const msalConfig: Configuration = {
  auth: {
    clientId: import.meta.env.VITE_ENTRA_CLIENT_ID || '<your-app-registration-client-id>',
    authority: `https://login.microsoftonline.com/${import.meta.env.VITE_ENTRA_TENANT_ID || '<your-tenant-id>'}`,
    redirectUri: window.location.origin,
  },
  cache: {
    cacheLocation: 'localStorage',
  },
}

export const msalInstance = new PublicClientApplication(msalConfig)

// Basic scopes for login — just need identity
export const loginRequest = {
  scopes: ['openid', 'profile', 'User.Read'],
}

/**
 * Get a Foundry-scoped access token for the current user.
 * Tries silent acquisition first, falls back to popup.
 */
export async function getAccessToken(): Promise<string | null> {
  const accounts = msalInstance.getAllAccounts()
  if (accounts.length === 0) return null

  const tokenRequest = {
    scopes: ['https://ai.azure.com/.default'],
    account: accounts[0],
  }

  try {
    const response = await msalInstance.acquireTokenSilent(tokenRequest)
    return response.accessToken
  } catch {
    try {
      const response = await msalInstance.acquireTokenPopup(tokenRequest)
      return response.accessToken
    } catch (e) {
      console.warn('Could not acquire Foundry token:', e)
      return null
    }
  }
}
