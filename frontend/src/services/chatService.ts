import type {
  ChatMessage,
  ChatMessageResponse,
  ChatResponse,
  ChatSession,
  ChatSessionResponse,
  ChatSessionSummaryResponse,
} from '../types'
import {
  clearConversation,
  createChatSession,
  deleteConversation,
  fetchChatSession,
  regenerateChatMessage,
} from '../lib/api'

export function mapChatMessage(m: ChatMessageResponse): ChatMessage {
  return {
    id: m.id,
    role: m.role,
    content: m.content,
    citations: m.citations ?? [],
    chunksUsed: m.chunks_used ?? 0,
    unavailable: Boolean(m.unavailable),
    createdAt: m.created_at,
    timestamp: m.created_at,
  }
}

export function mapChatSession(s: ChatSessionResponse): ChatSession {
  return {
    id: s.id,
    title: s.title,
    userId: s.user_id,
    createdAt: s.created_at,
    updatedAt: s.updated_at,
    selectedDocumentIds: s.selected_document_ids ?? [],
    revision: s.revision ?? 0,
    messages: (s.messages ?? []).map(mapChatMessage),
  }
}

/** Sidebar entries carry no messages; a chat's history loads when it is opened. */
export function mapChatSummary(s: ChatSessionSummaryResponse, userId: string): ChatSession {
  return {
    id: s.id,
    title: s.title,
    userId,
    createdAt: s.created_at,
    updatedAt: s.updated_at,
    selectedDocumentIds: s.selected_document_ids ?? [],
    revision: 0,
    messages: [],
  }
}

export async function getSession(id: string): Promise<ChatSession> {
  const session = await fetchChatSession(id)
  return mapChatSession(session)
}

export async function createSession(
  title: string,
  selectedDocumentIds: string[],
): Promise<ChatSession> {
  const created = await createChatSession({
    title,
    selected_document_ids: selectedDocumentIds,
  })
  return mapChatSession(created)
}

export async function clearSession(sessionId: string): Promise<void> {
  await clearConversation(sessionId)
}

export async function deleteSession(sessionId: string): Promise<void> {
  await deleteConversation(sessionId)
}

export async function regenerateSession(
  sessionId: string,
  messageId: string,
): Promise<ChatResponse> {
  return await regenerateChatMessage(sessionId, messageId)
}
