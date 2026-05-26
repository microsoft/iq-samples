/**
 * WebSocket client module
 * Provides connection management with automatic reconnection logic
 */

export type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'error'

export interface WebSocketMessage {
  type: string
  payload?: unknown
  [key: string]: unknown
}

export interface WebSocketHandlers {
  onStateChange?: (state: ConnectionState) => void | Promise<void>
  onMessage?: (message: WebSocketMessage) => void
  onError?: (error: Event) => void
}

const DEFAULT_URL = 'ws://localhost:8001/ws'
const MAX_RECONNECT_DELAY = 30000
const INITIAL_RECONNECT_DELAY = 1000

export function connectWebSocket(
  url: string = DEFAULT_URL,
  handlers: WebSocketHandlers = {}
): WebSocket {
  let reconnectDelay = INITIAL_RECONNECT_DELAY
  let reconnectTimeout: ReturnType<typeof setTimeout> | null = null
  let shouldReconnect = true

  const { onStateChange, onMessage, onError } = handlers

  const connect = (): WebSocket => {
    onStateChange?.('connecting')

    const ws = new WebSocket(url)

    ws.onopen = () => {
      reconnectDelay = INITIAL_RECONNECT_DELAY
      onStateChange?.('connected')
    }

    ws.onclose = () => {
      onStateChange?.('disconnected')

      if (shouldReconnect) {
        reconnectTimeout = setTimeout(() => {
          reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY)
          connect()
        }, reconnectDelay)
      }
    }

    ws.onerror = (event) => {
      onStateChange?.('error')
      onError?.(event)
    }

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as WebSocketMessage
        onMessage?.(message)
      } catch {
        console.warn('Received non-JSON message:', event.data)
      }
    }

    const originalClose = ws.close.bind(ws)
    ws.close = (code?: number, reason?: string) => {
      shouldReconnect = false
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout)
      }
      originalClose(code, reason)
    }

    return ws
  }

  return connect()
}

export function sendMessage(ws: WebSocket, message: WebSocketMessage): void {
  if (ws.readyState !== WebSocket.OPEN) {
    console.warn('WebSocket is not open. Current state:', ws.readyState)
    return
  }

  ws.send(JSON.stringify(message))
}

export function createMessage(type: string, payload?: unknown): WebSocketMessage {
  return { type, payload }
}
