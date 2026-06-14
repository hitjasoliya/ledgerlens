import type { ChatSession } from '../../types'
import { formatRelativeTime } from '../../lib/format'
import { Button } from '../ui/Button'
import { PlusIcon, MessageIcon, TrashIcon, CloseIcon } from '../ui/Icon'
import './ChatSidebar.css'

type Props = {
  sessions: ChatSession[]
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
  onClose?: () => void
}

export function ChatSidebar({ sessions, activeId, onSelect, onNew, onDelete, onClose }: Props) {
  return (
    <div className="chat-sidebar dark-scroll">
      <div className="chat-sidebar__top">
        <div className="chat-sidebar__top-row">
          <span className="chat-sidebar__label">Sessions</span>
          <div className="chat-sidebar__top-actions">
            <Button
              variant="primary"
              size="sm"
              leftIcon={<PlusIcon size={12} />}
              onClick={onNew}
            >
              New
            </Button>
            {onClose && (
              <button
                type="button"
                className="chat-sidebar__close-btn"
                onClick={onClose}
                aria-label="Close sidebar"
                title="Collapse sidebar"
              >
                <CloseIcon size={12} />
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="chat-sidebar__section-label">Recent</div>

      <div className="chat-sidebar__list">
        {sessions.length === 0 && (
          <div className="chat-sidebar__empty">-- no chats --</div>
        )}
        {sessions.map((session) => {
          const isActive = session.id === activeId
          const preview =
            session.messages[session.messages.length - 1]?.content?.slice(0, 60) ??
            '-- empty --'
          return (
            <button
              key={session.id}
              type="button"
              className={`chat-item ${isActive ? 'is-active' : ''}`}
              onClick={() => onSelect(session.id)}
            >
              <div className="chat-item__icon">
                <MessageIcon size={12} />
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
              {sessions.length > 1 && (
                <button
                  type="button"
                  className="chat-item__delete"
                  aria-label="Delete chat"
                  onClick={(e) => {
                    e.stopPropagation()
                    onDelete(session.id)
                  }}
                >
                  <TrashIcon size={12} />
                </button>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
