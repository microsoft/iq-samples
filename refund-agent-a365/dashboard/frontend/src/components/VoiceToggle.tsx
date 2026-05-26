import type { VoiceStatus } from '../hooks/useVoice'

export interface VoiceToggleProps {
  isEnabled: boolean
  isMuted: boolean
  isListening: boolean
  isSpeaking: boolean
  status: VoiceStatus
  onEnable: () => void
  onDisable: () => void
  onToggleMute: () => void
}

export function VoiceToggle({
  isEnabled,
  isMuted,
  isListening,
  isSpeaking,
  status,
  onEnable,
  onDisable,
  onToggleMute,
}: VoiceToggleProps) {
  const getButtonClasses = () => {
    const classes = ['icon-button-img']
    if (isEnabled) {
      if (isListening) classes.push('listening')
      if (isSpeaking) classes.push('speaking')
    }
    if (status === 'connecting') classes.push('connecting')
    return classes.join(' ')
  }

  const handleMainClick = () => {
    if (status === 'connecting') return
    if (isEnabled) {
      onDisable()
    } else {
      onEnable()
    }
  }

  const voiceIcon = isEnabled
    ? '/icons/active_voice_mode.png'
    : '/icons/inactive_voice_mode.png'

  const muteIcon = isMuted
    ? '/icons/active_mute.png'
    : '/icons/inactive_mute.png'

  return (
    <div className="voice-toggle">
      <button
        className={getButtonClasses()}
        onClick={handleMainClick}
        title={isEnabled ? 'Disable voice' : 'Enable voice'}
        disabled={status === 'connecting'}
      >
        <img src={voiceIcon} alt="Voice" className="button-icon" />
      </button>

      {isEnabled && status === 'connected' && (
        <button
          className="icon-button-img"
          onClick={onToggleMute}
          title={isMuted ? 'Unmute' : 'Mute'}
        >
          <img src={muteIcon} alt={isMuted ? 'Muted' : 'Unmuted'} className="button-icon" />
        </button>
      )}
    </div>
  )
}
