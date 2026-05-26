import { useState, useEffect, useRef, useCallback } from 'react'
import {
  connectWebSocket,
  sendMessage,
  createMessage,
  type ConnectionState,
  type WebSocketMessage,
} from '../lib/websocket'

const DEFAULT_URL = import.meta.env.DEV
  ? 'ws://localhost:8000/ws'
  : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`

export interface UseWebSocketOptions {
  url?: string
  onMessage?: (message: WebSocketMessage) => void
  getAccessToken?: () => Promise<string | null>
}

export interface UseWebSocketReturn {
  status: ConnectionState
  send: (message: object) => void
  connect: () => void
  disconnect: () => void
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const { url = DEFAULT_URL, onMessage, getAccessToken } = options
  const [status, setStatus] = useState<ConnectionState>('disconnected')
  const wsRef = useRef<WebSocket | null>(null)
  const urlRef = useRef(url)
  const onMessageRef = useRef(onMessage)
  const getAccessTokenRef = useRef(getAccessToken)

  urlRef.current = url
  onMessageRef.current = onMessage
  getAccessTokenRef.current = getAccessToken

  const connect = useCallback(() => {
    if (
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.OPEN ||
        wsRef.current.readyState === WebSocket.CONNECTING)
    ) {
      return
    }

    wsRef.current = connectWebSocket(urlRef.current, {
      onStateChange: async (state) => {
        setStatus(state)
        // Send auth token as first message on connect
        if (state === 'connected' && getAccessTokenRef.current && wsRef.current) {
          const token = await getAccessTokenRef.current()
          if (token) {
            sendMessage(wsRef.current, { type: 'auth', accessToken: token })
          }
        }
      },
      onMessage: (msg) => onMessageRef.current?.(msg),
      onError: (error) => {
        console.error('WebSocket error:', error)
      },
    })
  }, [])

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
  }, [])

  const send = useCallback((message: object) => {
    if (wsRef.current) {
      const wsMessage =
        'type' in message && typeof (message as Record<string, unknown>).type === 'string'
          ? (message as WebSocketMessage)
          : createMessage('message', message)
      sendMessage(wsRef.current, wsMessage)
    } else {
      console.warn('Cannot send message: WebSocket not connected')
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      disconnect()
    }
  }, [connect, disconnect])

  return {
    status,
    send,
    connect,
    disconnect,
  }
}
