import { useState } from 'react'
import type { ChatMessage as ChatMessageType } from '../../types'
import { Badge } from '../ui/Badge'
import { FileIcon } from '../ui/Icon'
import { formatTime } from '../../lib/format'
import { MarkdownRenderer } from './MarkdownRenderer'
import './ChatMessage.css'

type Props = {
  message: ChatMessageType
  userName: string
  onRegenerate?: () => void
  isLast?: boolean
}

export function ChatMessage({ message, userName, onRegenerate, isLast }: Props) {
  const isUser = message.role === 'user'
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // fallback
      const ta = document.createElement('textarea')
      ta.value = message.content
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    }
  }

  return (
    <div className={`chat-msg chat-msg--${message.role}`}>
      <div className="chat-msg__prefix">
        {isUser ? '>' : '|'}
      </div>
      <div className="chat-msg__content">
        <div className="chat-msg__author">
          {isUser ? userName.toUpperCase() : 'LEDGERLENS'}
          <span className="chat-msg__time">{formatTime(message.timestamp)}</span>
        </div>
        {message.attachedFile && (
          <div className="chat-msg__attachment">
            <FileIcon size={12} />
            <span>{message.attachedFile.name}</span>
          </div>
        )}
        <div className="chat-msg__bubble">
          {isUser ? (
            message.content
          ) : (
            <MarkdownRenderer content={message.content} />
          )}
        </div>
        {!isUser && message.citations && message.citations.length > 0 && (
          <div className="chat-msg__citations">
            <span className="chat-msg__citations-label">sources</span>
            {message.citations.map((c, i) => (
              <Badge key={`${i}-${c.page}`} tone="accent" size="sm">
                p.{c.page}
              </Badge>
            ))}
            {typeof message.chunksUsed === 'number' && (
              <Badge tone="neutral" size="sm">{message.chunksUsed} chunks</Badge>
            )}
          </div>
        )}
      </div>

      {!isUser && (
        <div className="chat-msg__actions">
          <button
            type="button"
            className={`chat-msg__action-btn ${copied ? 'chat-msg__action-btn--copied' : ''}`}
            onClick={handleCopy}
            title="Copy"
            aria-label="Copy message"
          >
            {copied ? 'OK' : 'C'}
          </button>
          {isLast && onRegenerate && (
            <button
              type="button"
              className="chat-msg__action-btn"
              onClick={onRegenerate}
              title="Regenerate"
              aria-label="Regenerate response"
            >
              R
            </button>
          )}
        </div>
      )}
    </div>
  )
}
