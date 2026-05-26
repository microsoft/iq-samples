/**
 * MSAL Configuration for Entra ID authentication
 * Uses the a365-cli-app registration in the cam3652606 tenant
 */
import { PublicClientApplication, type Configuration } from '@azure/msal-browser'

const msalConfig: Configuration = {
  auth: {
    clientId: 'ff57098a-9bac-4665-bc23-176f4fc2ba14',
    authority: 'https://login.microsoftonline.com/0ba24274-387c-4708-8823-ddec0a7043d1',
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
