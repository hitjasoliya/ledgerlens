import type { ChatMessage as ChatMessageType } from '../../types'
import { Avatar } from '../ui/Avatar'
import { Badge } from '../ui/Badge'
import { BotIcon, FileIcon } from '../ui/Icon'
import { formatTime } from '../../lib/format'
import './ChatMessage.css'

type Props = {
  message: ChatMessageType
  userName: string
}

export function ChatMessage({ message, userName }: Props) {
  const isUser = message.role === 'user'
  return (
    <div className={`chat-msg chat-msg--${message.role}`}>
      <div className="chat-msg__avatar">
        {isUser ? (
          <Avatar name={userName} size="md" variant="coral" />
        ) : (
          <div className="chat-msg__bot-avatar">
            <BotIcon size={18} />
          </div>
        )}
      </div>
      <div className="chat-msg__content">
        <div className="chat-msg__author">
          {isUser ? userName : 'adani_rag'}
          <span className="chat-msg__time">{formatTime(message.timestamp)}</span>
        </div>
        {message.attachedFile && (
          <div className="chat-msg__attachment">
            <FileIcon size={14} />
            <span>{message.attachedFile.name}</span>
          </div>
        )}
        <div className="chat-msg__bubble">{message.content}</div>
        {!isUser && message.citations && message.citations.length > 0 && (
          <div className="chat-msg__citations">
            <span className="chat-msg__citations-label">Sources</span>
            {message.citations.map((c, i) => (
              <Badge key={`${i}-${c.page}`} tone="coral">
                p.{c.page}
              </Badge>
            ))}
            {typeof message.chunksUsed === 'number' && (
              <Badge tone="neutral">{message.chunksUsed} chunks</Badge>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
