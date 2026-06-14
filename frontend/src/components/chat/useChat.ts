import { useCallback, useMemo, useState, useSyncExternalStore } from 'react'
import type { ChatMessage, ChatSession, FileEntry } from '../../types'
import {
  appendMessage,
  createSession,
  deleteSession,
  getSession,
  listSessions,
  setContextFile,
} from '../../services/chatService'
import { readJSON, StorageKeys, writeJSON } from '../../lib/storage'

function readAll(ownerId: string) {
  return readJSON<ChatSession[]>(StorageKeys.chats(ownerId), [])
}

function writeAll(ownerId: string, sessions: ChatSession[]) {
  writeJSON(StorageKeys.chats(ownerId), sessions)
}
import { sendMessage } from '../../lib/api'
import { bus, Topics } from '../../lib/eventBus'

type UseChatOptions = {
  ownerId: string
}

export type UseChatResult = {
  sessions: ChatSession[]
  activeSession: ChatSession | null
  loading: boolean
  error: string | null
  dismissError: () => void
  selectSession: (id: string) => void
  newSession: () => ChatSession
  removeSession: (id: string) => void
  send: (text: string, attachedFile?: FileEntry) => Promise<void>
  regenerate: () => Promise<void>
  attachContextFile: (fileId: string | undefined) => void
}

function ensureInitialSession(ownerId: string): ChatSession[] {
  const existing = listSessions(ownerId)
  if (existing.length > 0) return existing
  createSession(ownerId)
  return listSessions(ownerId)
}

type SessionsCacheRecord = { value: ChatSession[]; signature: string } | null
const sessionsCache = new Map<string, SessionsCacheRecord>()

function readSessionsSnapshot(ownerId: string): ChatSession[] {
  const next = ensureInitialSession(ownerId)
  const signature = JSON.stringify(next)
  const existing = sessionsCache.get(ownerId)
  if (existing && existing.signature === signature) return existing.value
  sessionsCache.set(ownerId, { value: next, signature })
  return next
}

function useSessionsStore(ownerId: string): ChatSession[] {
  const { snapshot, subscribe } = useMemo(() => {
    const topic = Topics.chats(ownerId)
    return {
      snapshot: () => readSessionsSnapshot(ownerId),
      subscribe: (listener: () => void) =>
        bus.subscribe(topic, () => {
          sessionsCache.delete(ownerId)
          listener()
        }),
    }
  }, [ownerId])
  return useSyncExternalStore(subscribe, snapshot, snapshot)
}

export function useChat({ ownerId }: UseChatOptions): UseChatResult {
  const sessions = useSessionsStore(ownerId)
  const [activeId, setActiveId] = useState<string | null>(() => {
    const initial = ensureInitialSession(ownerId)
    return initial[0]?.id ?? null
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const activeSession = useMemo(
    () => (activeId ? sessions.find((s) => s.id === activeId) ?? null : null),
    [sessions, activeId],
  )

  const selectSession = useCallback((id: string) => {
    setActiveId(id)
    setError(null)
  }, [])

  const newSession = useCallback(() => {
    setError(null)
    const created = createSession(ownerId)
    setActiveId(created.id)
    return created
  }, [ownerId])

  const removeSession = useCallback(
    (id: string) => {
      deleteSession(ownerId, id)
      const remaining = listSessions(ownerId)
      if (remaining.length === 0) {
        const created = createSession(ownerId)
        setActiveId(created.id)
        return
      }
      if (activeId === id) setActiveId(remaining[0].id)
    },
    [ownerId, activeId],
  )

  const attachContextFile = useCallback(
    (fileId: string | undefined) => {
      if (!activeId) return
      setContextFile(ownerId, activeId, fileId)
    },
    [ownerId, activeId],
  )

  const dismissError = useCallback(() => {
    setError(null)
  }, [])

  const send = useCallback(
    async (text: string, attachedFile?: FileEntry) => {
      if (!activeId) return
      const trimmed = text.trim()
      if (!trimmed) return

      setError(null)
      setLoading(true)

      const userMsg: Omit<ChatMessage, 'id' | 'timestamp'> = {
        role: 'user',
        content: trimmed,
        attachedFile: attachedFile
          ? { name: attachedFile.filename, fileId: attachedFile.id }
          : undefined,
      }
      appendMessage(ownerId, activeId, userMsg)

      try {
        const session = getSession(ownerId, activeId)
        if (!session) throw new Error('Active session not found')
        const res = await sendMessage(trimmed, ownerId, session.id)
        appendMessage(ownerId, activeId, {
          role: 'assistant',
          content: res.answer,
          citations: res.citations,
          chunksUsed: res.chunks_used,
        })
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err)
        setError(message)
        appendMessage(ownerId, activeId, {
          role: 'assistant',
          content: `Sorry, something went wrong: ${message}`,
        })
      } finally {
        setLoading(false)
      }
    },
    [ownerId, activeId],
  )

  const regenerate = useCallback(async () => {
    if (!activeId) return
    const session = getSession(ownerId, activeId)
    if (!session || session.messages.length === 0) return

    // Find last user message
    const lastUserIdx = [...session.messages].reverse().findIndex(m => m.role === 'user')
    if (lastUserIdx === -1) return

    const actualIdx = session.messages.length - 1 - lastUserIdx
    const lastUserMsg = session.messages[actualIdx]

    // Remove all messages after the last user message
    const sessions = readAll(ownerId)
    const si = sessions.findIndex(s => s.id === activeId)
    if (si !== -1) {
      sessions[si] = {
        ...session,
        messages: session.messages.slice(0, actualIdx + 1),
        updatedAt: Date.now(),
      }
      writeAll(ownerId, sessions)
    }

    // Re-send
    setError(null)
    setLoading(true)
    try {
      const res = await sendMessage(lastUserMsg.content, ownerId, session.id)
      appendMessage(ownerId, activeId, {
        role: 'assistant',
        content: res.answer,
        citations: res.citations,
        chunksUsed: res.chunks_used,
      })
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      setError(message)
      appendMessage(ownerId, activeId, {
        role: 'assistant',
        content: `Error: ${message}`,
      })
    } finally {
      setLoading(false)
    }
  }, [ownerId, activeId])

  return {
    sessions,
    activeSession,
    loading,
    error,
    dismissError,
    selectSession,
    newSession,
    removeSession,
    send,
    regenerate,
    attachContextFile,
  }
}
