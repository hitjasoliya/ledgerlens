import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { Button } from '../ui/Button'
import { PaperclipIcon, SendIcon, CloseIcon } from '../ui/Icon'
import './ChatInput.css'

type Props = {
  onSend: (text: string, file?: File) => void
  disabled?: boolean
  placeholder?: string
  allowFile?: boolean
  contextLabel?: string
  onClearContext?: () => void
}

export function ChatInput({
  onSend,
  disabled = false,
  placeholder = 'Ask a question about your documents...',
  allowFile = false,
  contextLabel,
  onClearContext,
}: Props) {
  const [value, setValue] = useState('')
  const [pendingFile, setPendingFile] = useState<File | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [value])

  const handleSubmit = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed, pendingFile ?? undefined)
    setValue('')
    setPendingFile(null)
    if (fileRef.current) fileRef.current.value = ''
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const handleFile = (f: File | null) => {
    if (!f) return
    if (!f.name.toLowerCase().endsWith('.pdf')) {
      alert('Only PDF files are supported')
      return
    }
    setPendingFile(f)
  }

  return (
    <div className="chat-input-wrap">
      {contextLabel && (
        <div className="chat-input__context">
          <span>Context:</span>
          <strong>{contextLabel}</strong>
          {onClearContext && (
            <button
              type="button"
              className="chat-input__context-clear"
              onClick={onClearContext}
              aria-label="Clear context"
            >
              <CloseIcon size={12} />
            </button>
          )}
        </div>
      )}

      <div className="chat-input">
        {pendingFile && (
          <div className="chat-input__pending-file">
            <span>{pendingFile.name}</span>
            <button
              type="button"
              onClick={() => {
                setPendingFile(null)
                if (fileRef.current) fileRef.current.value = ''
              }}
              aria-label="Remove file"
            >
              <CloseIcon size={12} />
            </button>
          </div>
        )}

        <textarea
          ref={textareaRef}
          className="chat-input__textarea"
          rows={1}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
        />

        <div className="chat-input__actions">
          {allowFile && (
            <>
              <input
                ref={fileRef}
                type="file"
                accept="application/pdf"
                hidden
                onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
              />
              <button
                type="button"
                className="chat-input__attach"
                onClick={() => fileRef.current?.click()}
                aria-label="Attach PDF"
                title="Attach a PDF for this message"
                disabled={disabled}
              >
                <PaperclipIcon size={16} />
              </button>
            </>
          )}
          <Button
            variant="primary"
            size="sm"
            onClick={handleSubmit}
            disabled={disabled || !value.trim()}
            aria-label="Send"
          >
            <SendIcon size={14} />
          </Button>
        </div>
      </div>

      <p className="chat-input__hint">
        Press <kbd>Enter</kbd> to send · <kbd>Shift + Enter</kbd> for newline
      </p>
    </div>
  )
}
