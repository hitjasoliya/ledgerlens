import type { ChatMessage, ChatSession } from '../types'
import { uid } from '../lib/ids'
import { readJSON, StorageKeys, writeJSON } from '../lib/storage'
import { bus, Topics } from '../lib/eventBus'

function readAll(ownerId: string): ChatSession[] {
  return readJSON<ChatSession[]>(StorageKeys.chats(ownerId), [])
}

function writeAll(ownerId: string, sessions: ChatSession[]): void {
  writeJSON(StorageKeys.chats(ownerId), sessions)
  bus.emit(Topics.chats(ownerId))
}

export function listSessions(ownerId: string): ChatSession[] {
  return readAll(ownerId).sort((a, b) => b.updatedAt - a.updatedAt)
}

export function getSession(ownerId: string, id: string): ChatSession | null {
  return readAll(ownerId).find((s) => s.id === id) ?? null
}

export function createSession(ownerId: string, title = 'New chat'): ChatSession {
  const now = Date.now()
  const session: ChatSession = {
    id: uid('chat'),
    title,
    ownerId,
    createdAt: now,
    updatedAt: now,
    messages: [],
  }
  writeAll(ownerId, [session, ...readAll(ownerId)])
  return session
}

export function deleteSession(ownerId: string, id: string): void {
  writeAll(
    ownerId,
    readAll(ownerId).filter((s) => s.id !== id),
  )
}

export function renameSession(
  ownerId: string,
  id: string,
  title: string,
): ChatSession | null {
  const sessions = readAll(ownerId)
  const idx = sessions.findIndex((s) => s.id === id)
  if (idx === -1) return null
  sessions[idx] = { ...sessions[idx], title, updatedAt: Date.now() }
  writeAll(ownerId, sessions)
  return sessions[idx]
}

export function appendMessage(
  ownerId: string,
  sessionId: string,
  message: Omit<ChatMessage, 'id' | 'timestamp'> & Partial<Pick<ChatMessage, 'id' | 'timestamp'>>,
): ChatSession | null {
  const sessions = readAll(ownerId)
  const idx = sessions.findIndex((s) => s.id === sessionId)
  if (idx === -1) return null

  const now = Date.now()
  const fullMessage: ChatMessage = {
    id: message.id ?? uid('msg'),
    role: message.role,
    content: message.content,
    citations: message.citations,
    chunksUsed: message.chunksUsed,
    attachedFile: message.attachedFile,
    timestamp: message.timestamp ?? now,
  }

  const session = sessions[idx]
  const isFirstUserMessage =
    fullMessage.role === 'user' &&
    !session.messages.some((m) => m.role === 'user')
  const title =
    isFirstUserMessage && session.title === 'New chat'
      ? deriveTitle(fullMessage.content)
      : session.title

  const updated: ChatSession = {
    ...session,
    title,
    messages: [...session.messages, fullMessage],
    updatedAt: now,
  }
  sessions[idx] = updated
  writeAll(ownerId, sessions)
  return updated
}

export function setContextFile(
  ownerId: string,
  sessionId: string,
  fileId: string | undefined,
): ChatSession | null {
  const sessions = readAll(ownerId)
  const idx = sessions.findIndex((s) => s.id === sessionId)
  if (idx === -1) return null
  sessions[idx] = {
    ...sessions[idx],
    contextFileId: fileId,
    updatedAt: Date.now(),
  }
  writeAll(ownerId, sessions)
  return sessions[idx]
}

function deriveTitle(text: string): string {
  const trimmed = text.trim().replace(/\s+/g, ' ')
  if (trimmed.length <= 48) return trimmed
  return `${trimmed.slice(0, 45)}…`
}
