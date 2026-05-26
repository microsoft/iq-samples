import { useState, useCallback, useRef, useEffect } from 'react'
import { useMsal } from '@azure/msal-react'
import { loginRequest, getAccessToken } from './lib/auth'
import { useWebSocket } from './hooks/useWebSocket'
import { useVoice } from './hooks/useVoice'
import { VoiceToggle } from './components/VoiceToggle'
import { ShipmentDashboard, type ShipmentData } from './components/ShipmentDashboard'
import { TypingIndicator } from './components/TypingIndicator'
import type { ChatMessage, ServerMessage } from './types/scenario'
import type { WebSocketMessage } from './lib/websocket'
import './App.css'

const EXAMPLE_QUESTIONS = [
  'How many packages are in the system?',
  'Show me all late deliveries',
  'Which hub has the highest throughput?',
]

function App() {
  const { instance, accounts, inProgress } = useMsal()
  const isAuthenticated = accounts.length > 0
  const isLoading = inProgress !== 'none'

  // Debug auth state
  console.log('MSAL state:', { accounts: accounts.length, inProgress, isAuthenticated, isLoading })
  console.log('All accounts:', instance.getAllAccounts())
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [inputText, setInputText] = useState('')
  const [isThinking, setIsThinking] = useState(false)
  const [thinkingText, setThinkingText] = useState('Thinking')
  const [shipmentData, setShipmentData] = useState<ShipmentData | null>(null)
  const [isLookingUp, setIsLookingUp] = useState(false)
  const [focusQuery, setFocusQuery] = useState<string | null>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)

  const handleLogin = () => {
    instance.loginRedirect(loginRequest).catch(console.error)
  }

  const handleLogout = () => {
    instance.logoutRedirect().catch(console.error)
  }

  const handleServerMessage = useCallback((msg: WebSocketMessage) => {
    const message = msg as unknown as ServerMessage

    switch (message.type) {
      case 'thinking':
        setIsThinking(true)
        setThinkingText('Thinking')
        break

      case 'tool_calling':
        setIsThinking(true)
        setThinkingText('Querying delivery network')
        setIsLookingUp(true)
        break

      case 'tool_result':
        setThinkingText('Processing results')
        setIsLookingUp(false)
        break

      case 'chat_message': {
        const chatMsg = message as unknown as { role: 'user' | 'assistant'; text: string }
        if (chatMsg.role === 'assistant') {
          setIsThinking(false)
        }
        setChatMessages(prev => [...prev, { role: chatMsg.role, text: chatMsg.text }])
        break
      }

      case 'shipment_data': {
        const data = (message as unknown as { payload: ShipmentData }).payload
        setShipmentData(data)
        if (data.focus_query) setFocusQuery(data.focus_query)
        setIsLookingUp(false)
        break
      }

      case 'error':
        setIsThinking(false)
        setIsLookingUp(false)
        break
    }
  }, [])

  const ws = useWebSocket({ onMessage: handleServerMessage, getAccessToken })

  const voice = useVoice({
    onTranscript: (role, text) => {
      if (role === 'assistant') {
        setIsThinking(false)
      }
      setChatMessages(prev => {
        if (role === 'assistant' && prev.length > 0 && prev[prev.length - 1].role === 'assistant') {
          const updated = [...prev]
          updated[updated.length - 1] = {
            ...updated[updated.length - 1],
            text: updated[updated.length - 1].text + text,
          }
          return updated
        }
        return [...prev, { role, text }]
      })
      if (role === 'user') {
        setFocusQuery(text)
      }
    },
    onUserSpeechEnd: () => {
      setIsThinking(true)
      setThinkingText('Thinking')
      setIsLookingUp(true)
    },
    onInterrupt: () => {
      setIsThinking(false)
    },
    onShipmentData: (payload) => {
      const data = payload as unknown as ShipmentData
      setShipmentData(data)
      if (data.focus_query) setFocusQuery(data.focus_query)
      setIsLookingUp(false)
      setIsThinking(false)
    },
  })

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages, isThinking])

  const handleSend = () => {
    if (!inputText.trim()) return
    setFocusQuery(inputText)
    ws.send({ type: 'chat', message: inputText })
    setInputText('')
    setIsThinking(true)
    setThinkingText('Thinking')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleNewChat = () => {
    setChatMessages([])
    setIsThinking(false)
    setShipmentData(null)
    setIsLookingUp(false)
    setFocusQuery(null)
  }

  const handleExampleClick = (q: string) => {
    setFocusQuery(q)
    ws.send({ type: 'chat', message: q })
    setIsThinking(true)
    setThinkingText('Thinking')
  }

  return (
    <div className="app">
      {/* Left: Chat Panel */}
      <div className="chat-panel">
        <div className="chat-header">
          <span className="header-title">Refund Agent</span>
          <div className="header-actions">
            {isAuthenticated && (
              <>
                <span className="user-name">{accounts[0]?.name || accounts[0]?.username}</span>
                <VoiceToggle
                  isEnabled={voice.isEnabled}
                  isMuted={voice.isMuted}
                  isListening={voice.isListening}
                  isSpeaking={voice.isSpeaking}
                  status={voice.status}
                  onEnable={voice.enable}
                  onDisable={voice.disable}
                  onToggleMute={voice.toggleMute}
                />
                <button
                  className="icon-button-img"
                  onClick={handleNewChat}
                  title="New conversation"
                >
                  <img src="/icons/new_conversation.png" alt="New" className="button-icon" />
                </button>
                <button className="sign-out-button" onClick={handleLogout} title="Sign out">
                  Sign out
                </button>
              </>
            )}
          </div>
        </div>

        <div className="chat-messages">
          {isLoading ? (
            <div className="chat-welcome">
              <p className="welcome-title">Signing in...</p>
            </div>
          ) : !isAuthenticated ? (
            <div className="chat-welcome">
              <p className="welcome-title">Shipment Coordinator</p>
              <p className="welcome-hint">Sign in with your Microsoft account to get started</p>
              <button className="sign-in-button" onClick={handleLogin}>
                Sign in
              </button>
            </div>
          ) : chatMessages.length === 0 ? (
            <div className="chat-welcome">
              <p className="welcome-title">Shipment Coordinator</p>
              <p className="welcome-hint">Ask about deliveries or try one below</p>
              <div className="welcome-examples">
                {EXAMPLE_QUESTIONS.map(q => (
                  <button
                    key={q}
                    className="example-button"
                    onClick={() => handleExampleClick(q)}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          {chatMessages.map((msg, i) => (
            <div key={i} className={`chat-message ${msg.role}`}>
              <div className="message-avatar">
                {msg.role === 'user' ? '\u{1F464}' : '\u{1F4E6}'}
              </div>
              <div className="message-content">{msg.text}</div>
            </div>
          ))}
          {isThinking && (
            <div className="chat-message assistant">
              <div className="message-avatar">{'\u{1F4E6}'}</div>
              <div className="message-content">
                <TypingIndicator text={thinkingText} />
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        <div className="chat-input-area">
          <input
            className="chat-input"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about shipments, deliveries, or logistics..."
            disabled={ws.status !== 'connected'}
          />
          <button
            className="send-button"
            onClick={handleSend}
            disabled={!inputText.trim() || ws.status !== 'connected'}
          >
            &#8593;
          </button>
        </div>

        <div className="chat-disclaimer">
          {ws.status === 'connected' ? 'Connected to Shipment Coordinator' : ws.status === 'connecting' ? 'Connecting...' : 'Disconnected'}
        </div>
      </div>

      {/* Right: Shipment Dashboard Panel */}
      <div className="viz-panel">
        <div className="viz-header">
          <div className="viz-header-left">
            <h2>Shipment Dashboard</h2>
          </div>
        </div>
        <ShipmentDashboard shipmentData={shipmentData} isLookingUp={isLookingUp} focusQuery={focusQuery} />
      </div>
    </div>
  )
}

export default App
