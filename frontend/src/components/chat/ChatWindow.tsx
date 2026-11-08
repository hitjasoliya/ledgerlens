import { useEffect, useMemo, useRef } from 'react'
import type { ReactNode } from 'react'
import type { ChatSession, FileEntry } from '../../types'
import { ChatMessage } from './ChatMessage'
import { ChatInput } from './ChatInput'
import { CloseIcon, FileIcon, LockIcon, TrashIcon } from '../ui/Icon'
import { Button } from '../ui/Button'
import './ChatWindow.css'

type Props = {
  leading?: ReactNode
  session: ChatSession | null
  loading: boolean
  error?: string | null
  onDismissError?: () => void
  onReloadSession?: () => void
  onSend: (text: string) => Promise<void> | void
  onRegenerate?: () => void
  onClearHistory?: () => void
  onNewChat?: () => void
  accessibleFiles?: FileEntry[]
}

const SUGGESTED_QUESTIONS = [
  'What were total revenues for the period?',
  'Summarize operating expenses and net income.',
  'What risk factors are mentioned?',
]

export function ChatWindow({
  leading,
  session,
  loading,
  error,
  onDismissError,
  onReloadSession,
  onSend,
  onRegenerate,
  onClearHistory,
  onNewChat,
  accessibleFiles = [],
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const messageCount = session?.messages.length ?? 0
  const isEmpty = messageCount === 0
  const selectedCount = session?.selectedDocumentIds.length ?? 0
  // Every chat is created with its documents, so "no chat" is the only state that needs them.
  const needsSources = !session

  const selectedNames = useMemo(() => {
    const byId = new Map(accessibleFiles.map((f) => [f.id, f.filename.replace(/\.pdf$/i, '')]))
    return (session?.selectedDocumentIds ?? []).map((id) => byId.get(id) ?? 'Unavailable document')
  }, [accessibleFiles, session?.selectedDocumentIds])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messageCount, loading])

  // A chat's documents are fixed when it is created; this only shows which ones.
  const sourcesPill =
    selectedCount === 0 ? null : (
      <span
        className="sources-pill"
        title={`This chat answers from: ${selectedNames.join(', ')}. Start a new chat to use other documents.`}
      >
        <LockIcon size={13} />
        {selectedCount} document{selectedCount === 1 ? '' : 's'}
      </span>
    )

  const composer = (
    <ChatInput
      onSend={onSend}
      disabled={loading || needsSources}
      autoFocus={isEmpty && !needsSources}
      placeholder={needsSources ? 'Choose documents to start' : 'Ask about your documents'}
      toolbar={sourcesPill}
    />
  )

  const scopeHint =
    needsSources
      ? null
      : 'Answers come only from these documents and cite the page. Start a new chat to use others.'

  return (
    <div className="chat">
      <header className="chat__bar">
        <div className="chat__bar-start">
          {leading}
          {!isEmpty && session && <h1 className="chat__title">{session.title}</h1>}
        </div>
        <div className="chat__bar-end">
          {!isEmpty && onClearHistory && (
            <button
              type="button"
              className="icon-btn"
              onClick={onClearHistory}
              disabled={loading}
              aria-label="Clear messages"
              title="Clear messages (keeps sources)"
            >
              <TrashIcon size={16} />
            </button>
          )}
        </div>
      </header>

      {error && (
        <div className="chat__notices">
          {error && (
            <div className="notice notice--danger" role="alert">
              <span>{error}</span>
              <span className="chat__notice-actions">
                {onReloadSession && (
                  <Button size="sm" variant="secondary" onClick={onReloadSession}>
                    Reload
                  </Button>
                )}
                {onDismissError && (
                  <button type="button" className="icon-btn icon-btn--sm" onClick={onDismissError} aria-label="Dismiss">
                    <CloseIcon size={14} />
                  </button>
                )}
              </span>
            </div>
          )}
        </div>
      )}

      {isEmpty ? (
        <div className="chat__welcome">
          <div className="chat__welcome-inner">
            <h2 className="chat__welcome-title">
              {needsSources ? 'Which documents should we look at?' : 'What do you want to know?'}
            </h2>
            {needsSources && (
              <Button size="lg" variant="primary" leftIcon={<FileIcon size={16} />} onClick={onNewChat} disabled={!onNewChat}>
                Choose documents
              </Button>
            )}
            {!needsSources && composer}
            {!needsSources && selectedNames.length > 0 && (
              <ul className="chat__scope" aria-label="Documents in this chat">
                {selectedNames.map((name, i) => (
                  <li key={`${i}-${name}`}>
                    <FileIcon size={12} />
                    <span>{name}</span>
                  </li>
                ))}
              </ul>
            )}
            {scopeHint && <p className="chat__hint">{scopeHint}</p>}
            {selectedCount > 0 && (
              <div className="chat__suggestions">
                {SUGGESTED_QUESTIONS.map((q) => (
                  <button
                    key={q}
                    type="button"
                    className="chat__suggestion"
                    onClick={() => void onSend(q)}
                    disabled={loading}
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      ) : (
        <>
          <div className="chat__scroll">
            <div className="chat__thread">
              {session?.messages.map((msg, i) => (
                <ChatMessage
                  key={msg.id}
                  message={msg}
                  isLast={i === messageCount - 1 && msg.role === 'assistant'}
                  onRegenerate={loading ? undefined : onRegenerate}
                />
              ))}
              {loading && (
                <div className="chat__thinking" role="status" aria-label="Generating answer">
                  <span />
                  <span />
                  <span />
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          </div>
          <div className="chat__dock">
            {composer}
            {scopeHint && <p className="chat__hint">{scopeHint}</p>}
          </div>
        </>
      )}
    </div>
  )
}
