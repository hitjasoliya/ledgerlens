import { useEffect, useMemo, useRef, useState } from 'react'
import type { ChatMessage as ChatMessageType } from '../../types'
import { CheckIcon, CopyIcon, FileIcon, RefreshIcon } from '../ui/Icon'
import { formatTime } from '../../lib/format'
import { fetchDocumentSourceBlob } from '../../lib/api'
import { MarkdownRenderer } from './MarkdownRenderer'
import { buildCitationView } from '../../lib/citations'
import './ChatMessage.css'

type Props = {
  message: ChatMessageType
  onRegenerate?: () => void
  isLast?: boolean
}

export function ChatMessage({ message, onRegenerate, isLast }: Props) {
  const isUser = message.role === 'user'
  const isUnavailable = !isUser && Boolean(message.unavailable)
  const [copied, setCopied] = useState(false)
  const [openingDocId, setOpeningDocId] = useState<string | null>(null)
  const [citationError, setCitationError] = useState<string | null>(null)
  const activeUrlsRef = useRef<Set<string>>(new Set())
  const view = useMemo(
    () => buildCitationView(message.content, message.citations ?? []),
    [message.content, message.citations],
  )

  // Revoke any created object URLs on unmount
  useEffect(() => {
    const urls = activeUrlsRef.current
    return () => {
      urls.forEach((url) => {
        try {
          URL.revokeObjectURL(url)
        } catch {
          // ignore
        }
      })
      urls.clear()
    }
  }, [])

  const handleCopy = async () => {
    if (isUnavailable) return
    try {
      await navigator.clipboard.writeText(view.plain)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      const ta = document.createElement('textarea')
      ta.value = view.plain
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    }
  }

  const handleOpenCitation = async (documentId: string, page: number) => {
    setCitationError(null)
    setOpeningDocId(documentId)

    // Keep the handle, then detach its opener before fetching protected content.
    const targetWin = window.open('about:blank', '_blank')
    if (!targetWin) {
      setOpeningDocId(null)
      setCitationError(
        'Popup blocked by browser. Please allow popups for LedgerLens to view source PDFs.',
      )
      return
    }

    targetWin.opener = null

    let objectUrl: string | null = null

    try {
      const blob = await fetchDocumentSourceBlob(documentId)
      objectUrl = URL.createObjectURL(blob)
      activeUrlsRef.current.add(objectUrl)

      targetWin.location.href = `${objectUrl}#page=${page}`

      // Revoke object URL after PDF viewer has loaded
      const currentUrl = objectUrl
      setTimeout(() => {
        try {
          URL.revokeObjectURL(currentUrl)
        } catch {
          // ignore
        }
        activeUrlsRef.current.delete(currentUrl)
      }, 60000)
    } catch (err) {
      if (objectUrl) {
        try {
          URL.revokeObjectURL(objectUrl)
        } catch {
          // ignore
        }
        activeUrlsRef.current.delete(objectUrl)
      }
      targetWin.close()
      const msg = err instanceof Error ? err.message : String(err)
      setCitationError(`Access denied or source unavailable: ${msg}`)
    } finally {
      setOpeningDocId(null)
    }
  }

  const sentAt = formatTime(message.timestamp || message.createdAt)

  if (isUser) {
    return (
      <div className="msg msg--user">
        {message.attachedFile && (
          <div className="msg__attachment">
            <FileIcon size={14} />
            <span>{message.attachedFile.name}</span>
          </div>
        )}
        <div className="msg__bubble" title={sentAt}>{message.content}</div>
      </div>
    )
  }

  const openSource = (n: number) => {
    const source = view.sources[n - 1]
    if (source) void handleOpenCitation(source.documentId, source.page)
  }
  const sourceLabel = (n: number) => {
    const source = view.sources[n - 1]
    return source ? `${source.filename}, page ${source.page}` : ''
  }

  return (
    <div className="msg msg--assistant">
      {isUnavailable ? (
        <div className="msg__unavailable" title={sentAt}>
          {message.content || 'This answer is unavailable.'}
        </div>
      ) : (
        <div className="msg__body" title={sentAt}>
          <MarkdownRenderer content={view.markdown} onCitation={openSource} citationLabel={sourceLabel} />
        </div>
      )}

      {!isUnavailable && view.sources.length > 0 && (
        <div className="msg__sources" aria-label="Sources">
          {view.sources.map((source) => {
            const opening = openingDocId === source.documentId
            return (
              <button
                key={source.n}
                type="button"
                className="msg__source"
                onClick={() => openSource(source.n)}
                disabled={opening}
                title={`Open ${source.filename} at page ${source.page}`}
              >
                <span className="msg__source-n">{source.n}</span>
                <span className="msg__source-name">{source.filename.replace(/\.pdf$/i, '')}</span>
                <span className="msg__source-page">{opening ? 'Opening…' : `p. ${source.page}`}</span>
              </button>
            )
          })}
        </div>
      )}

      {citationError && (
        <div className="notice notice--danger msg__citation-error" role="alert">
          {citationError}
        </div>
      )}

      {!isUnavailable && (
        <div className="msg__actions">
          <button
            type="button"
            className="icon-btn icon-btn--sm"
            onClick={handleCopy}
            aria-label={copied ? 'Copied' : 'Copy answer'}
            title={copied ? 'Copied' : 'Copy'}
          >
            {copied ? <CheckIcon size={14} /> : <CopyIcon size={14} />}
          </button>
          {isLast && onRegenerate && (
            <button
              type="button"
              className="icon-btn icon-btn--sm"
              onClick={onRegenerate}
              aria-label="Regenerate answer"
              title="Regenerate"
            >
              <RefreshIcon size={14} />
            </button>
          )}
        </div>
      )}
    </div>
  )
}
