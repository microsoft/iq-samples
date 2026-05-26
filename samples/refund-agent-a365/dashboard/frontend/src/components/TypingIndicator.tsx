export function TypingIndicator({ text = 'Thinking' }: { text?: string }) {
  return (
    <div className="thinking-content">
      <span className="thinking-text">{text}</span>
      <span className="thinking-dots-anim">
        <span>.</span><span>.</span><span>.</span>
      </span>
    </div>
  )
}
