import type { ChatSession } from '../../types'
import { formatRelativeTime } from '../../lib/format'
import { Button } from '../ui/Button'
import { PlusIcon, MessageIcon, TrashIcon } from '../ui/Icon'
import './ChatSidebar.css'

type Props = {
  sessions: ChatSession[]
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
}

export function ChatSidebar({ sessions, activeId, onSelect, onNew, onDelete }: Props) {
  return (
    <div className="chat-sidebar dark-scroll">
      <div className="chat-sidebar__top">
        <Button
          variant="primary"
          size="md"
          fullWidth
          leftIcon={<PlusIcon size={16} />}
          onClick={onNew}
        >
          New chat
        </Button>
      </div>

      <div className="chat-sidebar__section-label">Recent</div>

      <div className="chat-sidebar__list">
        {sessions.length === 0 && (
          <div className="chat-sidebar__empty">No chats yet</div>
        )}
        {sessions.map((session) => {
          const isActive = session.id === activeId
          const preview =
            session.messages[session.messages.length - 1]?.content?.slice(0, 60) ??
            'No messages yet'
          return (
            <button
              key={session.id}
              type="button"
              className={`chat-item ${isActive ? 'is-active' : ''}`}
              onClick={() => onSelect(session.id)}
            >
              <div className="chat-item__icon">
                <MessageIcon size={14} />
              </div>
              <div className="chat-item__body">
                <div className="chat-item__title">{session.title}</div>
                <div className="chat-item__meta">
                  <span className="chat-item__preview">{preview}</span>
                  <span className="chat-item__time">
                    {formatRelativeTime(session.updatedAt)}
                  </span>
                </div>
              </div>
              <button
                type="button"
                className="chat-item__delete"
                aria-label="Delete chat"
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete(session.id)
                }}
              >
                <TrashIcon size={14} />
              </button>
            </button>
          )
        })}
      </div>
    </div>
  )
}
