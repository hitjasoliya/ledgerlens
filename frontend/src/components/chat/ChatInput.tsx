import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'
import { ArrowUpIcon } from '../ui/Icon'
import './ChatInput.css'

type Props = {
  onSend: (text: string) => Promise<void> | void
  disabled?: boolean
  placeholder?: string
  toolbar?: ReactNode
  autoFocus?: boolean
}

export function ChatInput({
  onSend,
  disabled = false,
  placeholder = 'Ask about your documents',
  toolbar,
  autoFocus = false,
}: Props) {
  const [value, setValue] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`
  }, [value])

  const handleSubmit = async () => {
    const trimmed = value.trim()
    if (!trimmed || disabled || submitting) return
    setSubmitting(true)
    try {
      await onSend(trimmed)
      // Clear only after the send succeeds so a failure keeps the draft.
      setValue('')
    } catch {
      // The draft is preserved on failure.
    } finally {
      setSubmitting(false)
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      void handleSubmit()
    }
  }

  const canSend = !disabled && !submitting && value.trim().length > 0

  return (
    <div className="composer">
      <div className={`composer__box ${disabled ? 'is-disabled' : ''}`}>
        <textarea
          ref={textareaRef}
          className="composer__textarea"
          rows={1}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || submitting}
          autoFocus={autoFocus}
          aria-label="Message"
        />

        <div className="composer__bar">
          <div className="composer__tools">
            {toolbar}
          </div>

          <button
            type="button"
            className="composer__send"
            onClick={() => void handleSubmit()}
            disabled={!canSend}
            aria-label="Send message"
          >
            {submitting ? <span className="composer__spinner" aria-hidden /> : <ArrowUpIcon size={18} />}
          </button>
        </div>
      </div>
    </div>
  )
}
