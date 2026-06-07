import { useEffect, useMemo, useRef } from 'react'
import type { ChatSession, FileEntry } from '../../types'
import { ChatMessage } from './ChatMessage'
import { ChatInput } from './ChatInput'
import { EmptyState } from '../ui/EmptyState'
import { BotIcon, FileIcon, ChevronRightIcon, CloseIcon } from '../ui/Icon'
import './ChatWindow.css'

type Props = {
  session: ChatSession | null
  userName: string
  loading: boolean
  error?: string | null
  onDismissError?: () => void
  onSend: (text: string, file?: File) => void
  allowFile?: boolean
  contextFile?: FileEntry | null
  contextFiles?: FileEntry[]
  onPickContext?: (fileId: string) => void
  onClearContext?: () => void
}

export function ChatWindow({
  session,
  userName,
  loading,
  error,
  onDismissError,
  onSend,
  allowFile = false,
  contextFile,
  contextFiles,
  onPickContext,
  onClearContext,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [session?.messages.length, loading])

  const headerLabel = useMemo(() => {
    if (!session) return 'No chat selected'
    return session.title
  }, [session])

  return (
    <div className="chat-window">
      <header className="chat-window__header">
        <div className="chat-window__title">{headerLabel}</div>
        {contextFiles && contextFiles.length > 0 && onPickContext && (
          <ContextPicker
            files={contextFiles}
            activeId={contextFile?.id}
            onPick={onPickContext}
          />
        )}
      </header>

      {error && onDismissError && (
        <div className="chat-window__error" role="alert">
          <span className="chat-window__error-text">{error}</span>
          <button
            type="button"
            className="chat-window__error-dismiss"
            onClick={onDismissError}
            aria-label="Dismiss"
          >
            <CloseIcon size={14} />
          </button>
        </div>
      )}

      <div className="chat-window__body">
        {!session || session.messages.length === 0 ? (
          <div className="chat-window__empty">
            <EmptyState
              icon={<BotIcon size={28} />}
              title="Hi, I'm CapitalQuery"
              description={
                allowFile
                  ? 'Ask me about any document you have access to. You can also attach a PDF for this conversation.'
                  : 'Ask me about your enterprise documents and I will respond with cited answers.'
              }
            />
          </div>
        ) : (
          <div className="chat-window__messages">
            {session.messages.map((msg) => (
              <ChatMessage key={msg.id} message={msg} userName={userName} />
            ))}
            {loading && (
              <div className="chat-window__typing">
                <div className="chat-window__typing-avatar">
                  <BotIcon size={18} />
                </div>
                <div className="chat-window__typing-dots">
                  <span /><span /><span />
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <ChatInput
        onSend={onSend}
        disabled={loading || !session}
        allowFile={allowFile}
        contextLabel={contextFile?.filename}
        onClearContext={onClearContext}
      />
    </div>
  )
}

function ContextPicker({
  files,
  activeId,
  onPick,
}: {
  files: FileEntry[]
  activeId?: string
  onPick: (id: string) => void
}) {
  return (
    <div className="chat-window__context">
      <FileIcon size={14} />
      <select
        className="chat-window__context-select"
        value={activeId ?? ''}
        onChange={(e) => onPick(e.target.value)}
      >
        <option value="">Select a file as context…</option>
        {files.map((f) => (
          <option key={f.id} value={f.id}>
            {f.filename}
          </option>
        ))}
      </select>
      <ChevronRightIcon size={12} />
    </div>
  )
}
