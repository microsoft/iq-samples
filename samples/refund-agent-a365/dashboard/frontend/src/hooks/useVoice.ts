import { useState, useRef, useCallback, useEffect } from 'react'
import { pcm16ToFloat32, float32ToPcm16Base64, VOICE_SAMPLE_RATE } from '../lib/audioUtils'

const VOICE_WS_URL = 'ws://localhost:8000/voice'
const MAX_RECONNECT_DELAY = 30000
const INITIAL_RECONNECT_DELAY = 1000

export type VoiceStatus = 'disconnected' | 'connecting' | 'connected' | 'error'

export interface UseVoiceOptions {
  onTranscript?: (role: 'user' | 'assistant', text: string) => void
  onToolResult?: (tool: string, result: Record<string, unknown>) => void
  onError?: (error: string) => void
  onInterrupt?: () => void
  onUserSpeechEnd?: () => void
  onUserSpeechStart?: () => void
  onShipmentData?: (payload: Record<string, unknown>) => void
}

export interface UseVoiceReturn {
  isEnabled: boolean
  isMuted: boolean
  isListening: boolean
  isSpeaking: boolean
  status: VoiceStatus
  enable: () => Promise<void>
  disable: () => void
  toggleMute: () => void
}

interface VoiceMessage {
  type: string
  [key: string]: unknown
}

export function useVoice(options: UseVoiceOptions = {}): UseVoiceReturn {
  const { onTranscript, onToolResult, onError, onInterrupt, onUserSpeechEnd, onUserSpeechStart, onShipmentData } = options

  const [isEnabled, setIsEnabled] = useState(false)
  const [isMuted, setIsMuted] = useState(false)
  const [isListening, setIsListening] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [status, setStatus] = useState<VoiceStatus>('disconnected')

  const wsRef = useRef<WebSocket | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const playbackContextRef = useRef<AudioContext | null>(null)
  const mediaStreamRef = useRef<MediaStream | null>(null)
  const processorRef = useRef<ScriptProcessorNode | null>(null)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY)
  const shouldReconnectRef = useRef(false)
  const isMutedRef = useRef(false)
  const speakingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const audioQueueRef = useRef<Float32Array[]>([])
  const isPlayingRef = useRef(false)
  const nextPlayTimeRef = useRef(0)

  isMutedRef.current = isMuted

  const onTranscriptRef = useRef(onTranscript)
  const onToolResultRef = useRef(onToolResult)
  const onErrorRef = useRef(onError)
  const onInterruptRef = useRef(onInterrupt)
  const onUserSpeechEndRef = useRef(onUserSpeechEnd)
  const onUserSpeechStartRef = useRef(onUserSpeechStart)
  const onShipmentDataRef = useRef(onShipmentData)
  onTranscriptRef.current = onTranscript
  onToolResultRef.current = onToolResult
  onErrorRef.current = onError
  onInterruptRef.current = onInterrupt
  onUserSpeechEndRef.current = onUserSpeechEnd
  onUserSpeechStartRef.current = onUserSpeechStart
  onShipmentDataRef.current = onShipmentData

  const currentSourceRef = useRef<AudioBufferSourceNode | null>(null)

  const stopPlayback = useCallback(() => {
    if (currentSourceRef.current) {
      try {
        currentSourceRef.current.stop()
      } catch {
        // Already stopped
      }
      currentSourceRef.current = null
    }
    audioQueueRef.current = []
    nextPlayTimeRef.current = 0
    isPlayingRef.current = false
    setIsSpeaking(false)
  }, [])

  const playNextAudioChunk = useCallback(() => {
    const playbackContext = playbackContextRef.current
    if (!playbackContext || playbackContext.state === 'closed') {
      return
    }

    while (audioQueueRef.current.length > 0) {
      const float32 = audioQueueRef.current.shift()!

      const buffer = playbackContext.createBuffer(1, float32.length, VOICE_SAMPLE_RATE)
      buffer.getChannelData(0).set(float32)

      const duration = float32.length / VOICE_SAMPLE_RATE

      const now = playbackContext.currentTime
      const startTime = Math.max(now, nextPlayTimeRef.current)

      const source = playbackContext.createBufferSource()
      currentSourceRef.current = source
      source.buffer = buffer
      source.connect(playbackContext.destination)
      source.start(startTime)

      nextPlayTimeRef.current = startTime + duration
      isPlayingRef.current = true
    }
  }, [])

  const handleMessage = useCallback((event: MessageEvent) => {
    try {
      const message = JSON.parse(event.data) as VoiceMessage

      switch (message.type) {
        case 'status':
          if (message.status === 'connected') {
            setStatus('connected')
            reconnectDelayRef.current = INITIAL_RECONNECT_DELAY
          } else if (message.status === 'error') {
            setStatus('error')
            onErrorRef.current?.(message.error as string || 'Connection error')
          }
          break

        case 'speech_started':
          setIsListening(true)
          stopPlayback()
          onInterruptRef.current?.()
          onUserSpeechStartRef.current?.()
          break

        case 'speech_stopped':
          setIsListening(false)
          onUserSpeechEndRef.current?.()
          break

        case 'audio': {
          const base64 = message.data as string
          const float32 = pcm16ToFloat32(base64)
          audioQueueRef.current.push(float32)
          playNextAudioChunk()

          setIsSpeaking(true)
          if (speakingTimeoutRef.current) {
            clearTimeout(speakingTimeoutRef.current)
          }
          speakingTimeoutRef.current = setTimeout(() => {
            setIsSpeaking(false)
          }, 500)
          break
        }

        case 'transcript':
          onTranscriptRef.current?.(
            message.role as 'user' | 'assistant',
            message.text as string
          )
          break

        case 'tool_result':
          onToolResultRef.current?.(
            message.tool as string,
            message.result as Record<string, unknown>
          )
          break

        case 'shipment_data':
          onShipmentDataRef.current?.(
            message.payload as Record<string, unknown>
          )
          break

        case 'error':
          onErrorRef.current?.(message.error as string)
          break
      }
    } catch (err) {
      console.warn('Failed to parse voice message:', err)
    }
  }, [playNextAudioChunk, stopPlayback])

  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN ||
        wsRef.current?.readyState === WebSocket.CONNECTING) {
      return
    }

    setStatus('connecting')
    const ws = new WebSocket(VOICE_WS_URL)

    ws.onclose = () => {
      setStatus('disconnected')
      setIsListening(false)
      setIsSpeaking(false)

      if (shouldReconnectRef.current) {
        reconnectTimeoutRef.current = setTimeout(() => {
          reconnectDelayRef.current = Math.min(
            reconnectDelayRef.current * 2,
            MAX_RECONNECT_DELAY
          )
          connectWebSocket()
        }, reconnectDelayRef.current)
      }
    }

    ws.onerror = () => {
      setStatus('error')
    }

    ws.onmessage = handleMessage

    wsRef.current = ws
  }, [handleMessage])

  const startMicCapture = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      mediaStreamRef.current = stream

      const audioContext = new AudioContext({ sampleRate: VOICE_SAMPLE_RATE })
      audioContextRef.current = audioContext

      const source = audioContext.createMediaStreamSource(stream)

      const processor = audioContext.createScriptProcessor(4096, 1, 1)
      processorRef.current = processor

      processor.onaudioprocess = (e) => {
        if (!isMutedRef.current && wsRef.current?.readyState === WebSocket.OPEN) {
          const inputData = e.inputBuffer.getChannelData(0)
          const pcm16Base64 = float32ToPcm16Base64(inputData)
          wsRef.current.send(JSON.stringify({ type: 'audio', data: pcm16Base64 }))
        }
      }

      source.connect(processor)
      processor.connect(audioContext.destination)

    } catch (err) {
      console.error('Failed to start mic capture:', err)
      onErrorRef.current?.('Microphone access denied or unavailable')
      throw err
    }
  }, [])

  const stopMicCapture = useCallback(() => {
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop())
      mediaStreamRef.current = null
    }

    if (processorRef.current) {
      processorRef.current.disconnect()
      processorRef.current = null
    }

    if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
      audioContextRef.current.close()
      audioContextRef.current = null
    }
  }, [])

  const enable = useCallback(async () => {
    if (isEnabled) return

    try {
      playbackContextRef.current = new AudioContext({ sampleRate: VOICE_SAMPLE_RATE })

      await startMicCapture()

      shouldReconnectRef.current = true
      connectWebSocket()

      setIsEnabled(true)
      setIsMuted(true)
    } catch (err) {
      stopMicCapture()
      if (playbackContextRef.current && playbackContextRef.current.state !== 'closed') {
        playbackContextRef.current.close()
        playbackContextRef.current = null
      }
      throw err
    }
  }, [isEnabled, startMicCapture, connectWebSocket, stopMicCapture])

  const disable = useCallback(() => {
    shouldReconnectRef.current = false

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }

    if (speakingTimeoutRef.current) {
      clearTimeout(speakingTimeoutRef.current)
      speakingTimeoutRef.current = null
    }

    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }

    stopMicCapture()

    if (playbackContextRef.current && playbackContextRef.current.state !== 'closed') {
      playbackContextRef.current.close()
      playbackContextRef.current = null
    }

    audioQueueRef.current = []
    isPlayingRef.current = false

    setIsEnabled(false)
    setIsMuted(false)
    setIsListening(false)
    setIsSpeaking(false)
    setStatus('disconnected')
    reconnectDelayRef.current = INITIAL_RECONNECT_DELAY
  }, [stopMicCapture])

  const toggleMute = useCallback(() => {
    const newMuted = !isMutedRef.current
    isMutedRef.current = newMuted
    setIsMuted(newMuted)
  }, [])

  useEffect(() => {
    return () => {
      disable()
    }
  }, [disable])

  return {
    isEnabled,
    isMuted,
    isListening,
    isSpeaking,
    status,
    enable,
    disable,
    toggleMute,
  }
}
