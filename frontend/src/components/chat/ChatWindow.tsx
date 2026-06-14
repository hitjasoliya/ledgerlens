import { useEffect, useMemo, useRef } from 'react'
import type { ChatSession, FileEntry } from '../../types'
import { ChatMessage } from './ChatMessage'
import { ChatInput } from './ChatInput'
import { FileIcon, ChevronRightIcon, CloseIcon } from '../ui/Icon'
import './ChatWindow.css'

type Props = {
  session: ChatSession | null
  userName: string
  loading: boolean
  error?: string | null
  onDismissError?: () => void
  onSend: (text: string, file?: File) => void
  onRegenerate?: () => void
  allowFile?: boolean
  contextFile?: FileEntry | null
  contextFiles?: FileEntry[]
  onPickContext?: (fileId: string) => void
  onClearContext?: () => void
  sidebarOpen?: boolean
  onToggleSidebar?: () => void
}

const SUGGESTED_QUESTIONS = [
  'Summarize the key financial highlights',
  'What was the revenue and how did it change YoY?',
  'Show me EBITDA trends in a table',
  'What were the major risks or concerns mentioned?',
]

export function ChatWindow({
  session,
  userName,
  loading,
  error,
  onDismissError,
  onSend,
  onRegenerate,
  allowFile = false,
  contextFile,
  contextFiles,
  onPickContext,
  onClearContext,
  sidebarOpen = true,
  onToggleSidebar,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [session?.messages.length, loading])

  const headerLabel = useMemo(() => {
    if (!session) return 'No session'
    return session.title
  }, [session])

  return (
    <div className="chat-window">
      <header className="chat-window__header">
        {onToggleSidebar && (
          <button
            type="button"
            className="chat-window__sidebar-toggle"
            onClick={onToggleSidebar}
            title={sidebarOpen ? 'Collapse sessions' : 'Show sessions'}
            aria-label={sidebarOpen ? 'Collapse sessions' : 'Show sessions'}
          >
            {sidebarOpen ? '<<' : '>>'}
          </button>
        )}
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
            <CloseIcon size={12} />
          </button>
        </div>
      )}

      <div className="chat-window__body">
        {!session || session.messages.length === 0 ? (
          <div className="chat-window__empty">
            <div className="chat-window__empty-content">
              <div className="chat-window__empty-prompt">
                <span className="chat-window__empty-prompt-prefix">$</span>
                <span>capitalquery --ready</span>
              </div>
              <p className="chat-window__empty-desc">
                {allowFile
                  ? 'Ask about your documents or attach a PDF to begin.'
                  : 'Ask about your enterprise documents to begin.'}
              </p>
              <div className="chat-window__suggestions">
                {SUGGESTED_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    type="button"
                    className="chat-window__suggestion-chip"
                    onClick={() => onSend(q)}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="chat-window__messages">
            {session.messages.map((msg, i) => (
              <ChatMessage
                key={msg.id}
                message={msg}
                userName={userName}
                isLast={i === session.messages.length - 1 && msg.role === 'assistant'}
                onRegenerate={onRegenerate}
              />
            ))}
            {loading && (
              <div className="chat-window__typing">
                <div className="chat-window__typing-indicator">
                  <span>processing</span>
                  <span className="chat-window__typing-dot">.</span>
                  <span className="chat-window__typing-dot">.</span>
                  <span className="chat-window__typing-dot">.</span>
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
      <FileIcon size={12} />
      <select
        className="chat-window__context-select"
        value={activeId ?? ''}
        onChange={(e) => onPick(e.target.value)}
      >
        <option value="">context file...</option>
        {files.map((f) => (
          <option key={f.id} value={f.id}>
            {f.filename}
          </option>
        ))}
      </select>
      <ChevronRightIcon size={10} />
    </div>
  )
}
