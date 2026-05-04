import type { ChatResponse, IngestResponse } from '../types'

const API_BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

async function parseError(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: unknown }
    if (typeof data.detail === 'string') return data.detail
    if (Array.isArray(data.detail))
      return data.detail.map((d) => String(d)).join(', ')
    return res.statusText || `HTTP ${res.status}`
  } catch {
    return res.statusText || `HTTP ${res.status}`
  }
}

export async function sendMessage(
  message: string,
  userId: string,
  sessionId: string,
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, user_id: userId, session_id: sessionId }),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return (await res.json()) as ChatResponse
}

export async function clearConversation(): Promise<void> {
  const res = await fetch(`${API_BASE}/api/chat/clear`, { method: 'POST' })
  if (!res.ok) throw new Error(await parseError(res))
}

export type IngestOptions = {
  file: File
  userId: string
  sessionId: string
  isPersistent: boolean
  allowedUsers: string[]
}

export async function ingestPdf(opts: IngestOptions): Promise<IngestResponse> {
  const form = new FormData()
  form.append('file', opts.file)
  form.append('user_id', opts.userId)
  form.append('session_id', opts.sessionId)
  form.append('is_persistent', opts.isPersistent ? 'true' : 'false')
  form.append('allowed_users', opts.allowedUsers.join(','))

  const res = await fetch(`${API_BASE}/api/ingest`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) throw new Error(await parseError(res))
  return (await res.json()) as IngestResponse
}

export async function endSession(sessionId: string): Promise<void> {
  const form = new FormData()
  form.append('session_id', sessionId)
  const res = await fetch(`${API_BASE}/api/session/end`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) throw new Error(await parseError(res))
}

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`)
    return res.ok
  } catch {
    return false
  }
}
