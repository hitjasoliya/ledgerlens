import { useCallback, useEffect, useRef, useState } from 'react'
import type { ChatSession } from '../../types'
import {
  clearSession,
  createSession,
  deleteSession,
  getSession,
  mapChatSession,
  mapChatSummary,
  regenerateSession,
} from '../../services/chatService'
import { fetchChatSession, fetchChatSessions, sendMessage } from '../../lib/api'
import { waitForDocumentsSearchable } from '../../services/fileService'

type UseChatOptions = {
  ownerId: string
}

export type UseChatResult = {
  sessions: ChatSession[]
  activeSession: ChatSession | null
  loading: boolean
  initialLoading: boolean
  error: string | null
  dismissError: () => void
  selectSession: (id: string) => Promise<void>
  newSession: (selectedDocumentIds: string[]) => Promise<ChatSession>
  removeSession: (id: string) => Promise<void>
  clearHistory: () => Promise<void>
  send: (text: string) => Promise<void>
  regenerate: () => Promise<void>
  reloadSession: () => Promise<void>
}

export function useChat({ ownerId }: UseChatOptions): UseChatResult {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [activeSession, setActiveSession] = useState<ChatSession | null>(null)
  const [loading, setLoading] = useState(false)
  const [initialLoading, setInitialLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Generations to guard against race conditions and stale async completions
  const ownerGenRef = useRef(0)
  const sessionGenRef = useRef(0)

  // Load session list on startup / owner change
  useEffect(() => {
    ownerGenRef.current += 1
    const thisOwnerGen = ownerGenRef.current
    const controller = new AbortController()

    fetchChatSessions(controller.signal)
      .then(async (loaded) => {
        if (controller.signal.aborted || ownerGenRef.current !== thisOwnerGen) return
        const mapped = loaded
          .map((summary) => mapChatSummary(summary, ownerId))
          .sort((a, b) => b.updatedAt - a.updatedAt)

        if (mapped.length === 0) {
          // No chat yet: the UI asks for sources and creates the first chat with them.
          setSessions([])
        } else {
          setSessions(mapped)
          const first = mapped[0]
          sessionGenRef.current += 1
          const thisSessionGen = sessionGenRef.current
          setActiveId(first.id)

          try {
            const detail = await fetchChatSession(first.id, controller.signal)
            if (
              controller.signal.aborted ||
              ownerGenRef.current !== thisOwnerGen ||
              sessionGenRef.current !== thisSessionGen
            ) {
              return
            }
            setActiveSession(mapChatSession(detail))
          } catch {
            if (
              controller.signal.aborted ||
              ownerGenRef.current !== thisOwnerGen ||
              sessionGenRef.current !== thisSessionGen
            ) {
              return
            }
            setActiveSession(first)
          }
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted && ownerGenRef.current === thisOwnerGen) {
          setError(err instanceof Error ? err.message : String(err))
        }
      })
      .finally(() => {
        if (!controller.signal.aborted && ownerGenRef.current === thisOwnerGen) {
          setInitialLoading(false)
        }
      })

    return () => {
      controller.abort()
    }
  }, [ownerId])

  const selectSession = useCallback(
    async (id: string) => {
      if (loading) return // Serialise mutations while busy
      const thisOwnerGen = ownerGenRef.current
      sessionGenRef.current += 1
      const thisSessionGen = sessionGenRef.current

      setError(null)
      const priorActive = activeSession

      try {
        const detail = await getSession(id)
        if (
          ownerGenRef.current !== thisOwnerGen ||
          sessionGenRef.current !== thisSessionGen
        ) {
          return // Stale generation discarded
        }
        setActiveId(detail.id)
        setActiveSession(detail)
      } catch (err) {
        if (
          ownerGenRef.current !== thisOwnerGen ||
          sessionGenRef.current !== thisSessionGen
        ) {
          return
        }
        // Do not leave mismatched activeId and activeSession on load failure
        setActiveId(priorActive?.id ?? null)
        setActiveSession(priorActive)
        setError(err instanceof Error ? err.message : String(err))
      }
    },
    [loading, activeSession],
  )

  const reloadSession = useCallback(async () => {
    if (!activeId) return
    const thisOwnerGen = ownerGenRef.current
    const thisSessionGen = sessionGenRef.current

    try {
      const detail = await getSession(activeId)
      if (
        ownerGenRef.current !== thisOwnerGen ||
        sessionGenRef.current !== thisSessionGen
      ) {
        return
      }
      setActiveSession(detail)
      setSessions((prev) =>
        prev.map((s) => (s.id === detail.id ? detail : s)),
      )
      setError(null)
    } catch (err) {
      if (
        ownerGenRef.current !== thisOwnerGen ||
        sessionGenRef.current !== thisSessionGen
      ) {
        return
      }
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [activeId])

  const newSession = useCallback(async (selectedDocumentIds: string[]): Promise<ChatSession> => {
    if (loading) throw new Error('Cannot create session while request in flight')
    const thisOwnerGen = ownerGenRef.current
    sessionGenRef.current += 1
    const thisSessionGen = sessionGenRef.current

    setError(null)
    const created = await createSession('New chat', selectedDocumentIds)
    if (
      ownerGenRef.current !== thisOwnerGen ||
      sessionGenRef.current !== thisSessionGen
    ) {
      return created
    }

    setSessions((prev) => [created, ...prev])
    setActiveId(created.id)
    setActiveSession(created)
    return created
  }, [loading])

  const removeSession = useCallback(
    async (id: string) => {
      if (loading) return
      const confirmed = window.confirm(
        'Are you sure you want to permanently delete this chat session? Message history will be deleted. (Uploaded documents will remain intact.)',
      )
      if (!confirmed) return

      try {
        await deleteSession(id)
        const remaining = sessions.filter((s) => s.id !== id)
        setSessions(remaining)

        if (remaining.length === 0) {
          // Last chat gone: the UI asks for sources before creating another.
          setActiveId(null)
          setActiveSession(null)
          return
        }

        if (activeId === id) {
          const next = remaining[0]
          setActiveId(next.id)
          const detail = await getSession(next.id)
          setActiveSession(detail)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
      }
    },
    [sessions, activeId, loading],
  )

  const clearHistory = useCallback(async () => {
    if (!activeSession || loading) return
    const confirmed = window.confirm(
      'Clear all messages in this conversation? Document selection and lock state will be preserved.',
    )
    if (!confirmed) return

    try {
      await clearSession(activeSession.id)
      const detail = await getSession(activeSession.id)
      setActiveSession(detail)
      setSessions((prev) =>
        prev.map((s) => (s.id === detail.id ? detail : s)),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
  }, [activeSession, loading])

  const dismissError = useCallback(() => {
    setError(null)
  }, [])

  const send = useCallback(
    async (text: string) => {
      if (!activeSession || loading) return
      const trimmed = text.trim()
      if (!trimmed) return

      const thisOwnerGen = ownerGenRef.current
      const thisSessionGen = sessionGenRef.current
      const targetSessionId = activeSession.id

      setError(null)
      setLoading(true)

      let questionAccepted = false

      try {
        // Selected sources may still be indexing; wait until they are searchable.
        if (activeSession.selectedDocumentIds.length > 0) {
          await waitForDocumentsSearchable(activeSession.selectedDocumentIds)
        }

        // Submit question to authoritative backend
        await sendMessage(trimmed, targetSessionId)
        questionAccepted = true

    
        // Refresh authoritative history
        try {
          const reloaded = await getSession(targetSessionId)
          if (
            ownerGenRef.current === thisOwnerGen &&
            sessionGenRef.current === thisSessionGen
          ) {
            setActiveSession(reloaded)
            setSessions((prev) =>
              prev.map((s) => (s.id === reloaded.id ? reloaded : s)),
            )
          }
        } catch (reloadErr) {
          // Question was accepted on backend! Do not re-throw as unsent (avoids duplicate prompt)
          const msg =
            reloadErr instanceof Error ? reloadErr.message : String(reloadErr)
          setError(
            `Question accepted, but history reload failed: ${msg}. Click reload to refresh.`,
          )
        }
      } catch (err) {
        if (questionAccepted) {
          return
        }

        const msg = err instanceof Error ? err.message : String(err)
        setError(msg)

        // Backend locks first accepted question before provider generation;
        // if 503 or error occurs during chat, refresh authoritative state so
        // UI does not stay on an outdated unlocked revision/selection state.
        try {
          const fresh = await getSession(targetSessionId)
          if (
            ownerGenRef.current === thisOwnerGen &&
            sessionGenRef.current === thisSessionGen
          ) {
            setActiveSession(fresh)
            setSessions((prev) =>
              prev.map((s) => (s.id === fresh.id ? fresh : s)),
            )
          }
        } catch {
          // ignore reload error during failure recovery
        }

        // Re-throw so the composer keeps the draft
        throw err
      } finally {
        if (ownerGenRef.current === thisOwnerGen) {
          setLoading(false)
        }
      }
    },
    [activeSession, loading],
  )

  const regenerate = useCallback(async () => {
    if (!activeSession || loading) return
    const assistantMsgs = activeSession.messages.filter(
      (m) => m.role === 'assistant',
    )
    if (assistantMsgs.length === 0) return
    const lastAssistant = assistantMsgs[assistantMsgs.length - 1]

    const thisOwnerGen = ownerGenRef.current
    const thisSessionGen = sessionGenRef.current
    const targetSessionId = activeSession.id

    setError(null)
    setLoading(true)

    try {
      await regenerateSession(targetSessionId, lastAssistant.id)
      const reloaded = await getSession(targetSessionId)
      if (
        ownerGenRef.current === thisOwnerGen &&
        sessionGenRef.current === thisSessionGen
      ) {
        setActiveSession(reloaded)
        setSessions((prev) =>
          prev.map((s) => (s.id === reloaded.id ? reloaded : s)),
        )
      }
    } catch (err) {
      if (
        ownerGenRef.current === thisOwnerGen &&
        sessionGenRef.current === thisSessionGen
      ) {
        setError(err instanceof Error ? err.message : String(err))
      }
    } finally {
      if (ownerGenRef.current === thisOwnerGen) {
        setLoading(false)
      }
    }
  }, [activeSession, loading])

  return {
    sessions,
    activeSession,
    loading,
    initialLoading,
    error,
    dismissError,
    selectSession,
    newSession,
    removeSession,
    clearHistory,
    send,
    regenerate,
    reloadSession,
  }
}
