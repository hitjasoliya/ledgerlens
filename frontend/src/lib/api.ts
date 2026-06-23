import type { ChatResponse, IngestResponse } from '../types'

export const API_BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

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

function getAuthHeader(): Record<string, string> {
  try {
    const raw = localStorage.getItem('ledgerlens.session')
    if (raw) {
      const parsed = JSON.parse(raw) as { token?: string }
      if (parsed.token) {
        return { Authorization: `Bearer ${parsed.token}` }
      }
    }
  } catch {
    // ignore
  }
  return {}
}

export async function sendMessage(
  message: string,
  userId: string,
  sessionId: string,
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: 'POST',
    headers: { 
      'Content-Type': 'application/json',
      ...getAuthHeader()
    },
    body: JSON.stringify({ message, user_id: userId, session_id: sessionId }),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return (await res.json()) as ChatResponse
}

export async function clearConversation(): Promise<void> {
  const res = await fetch(`${API_BASE}/api/chat/clear`, { 
    method: 'POST',
    headers: { ...getAuthHeader() }
  })
  if (!res.ok) throw new Error(await parseError(res))
}

export async function deleteConversation(sessionId: string): Promise<void> {
  const form = new FormData()
  form.append('session_id', sessionId)
  const res = await fetch(`${API_BASE}/api/chat/delete`, { 
    method: 'POST',
    headers: { ...getAuthHeader() },
    body: form
  })
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
    headers: { ...getAuthHeader() },
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
    headers: { ...getAuthHeader() },
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

// Backend Auth APIs
export async function loginUser(
  username: string,
  password: string,
  role: string,
): Promise<{ access_token: string; user: any }> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, role }),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return (await res.json()) as { access_token: string; user: any }
}

export async function getProfile(): Promise<any> {
  const res = await fetch(`${API_BASE}/api/auth/me`, {
    method: 'GET',
    headers: { ...getAuthHeader() },
  })
  if (!res.ok) throw new Error(await parseError(res))
  return await res.json()
}

export async function fetchUsers(): Promise<any[]> {
  const res = await fetch(`${API_BASE}/api/users`, {
    method: 'GET',
    headers: { ...getAuthHeader() },
  })
  if (!res.ok) throw new Error(await parseError(res))
  return (await res.json()) as any[]
}

export async function saveUser(input: any): Promise<any> {
  const res = await fetch(`${API_BASE}/api/users`, {
    method: 'POST',
    headers: { 
      'Content-Type': 'application/json',
      ...getAuthHeader()
    },
    body: JSON.stringify(input),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return await res.json()
}

export async function removeUser(userId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/users/${userId}`, {
    method: 'DELETE',
    headers: { ...getAuthHeader() },
  })
  if (!res.ok) throw new Error(await parseError(res))
}

export async function previewLayout(file: File): Promise<any> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API_BASE}/api/admin/layout-preview`, {
    method: 'POST',
    headers: { ...getAuthHeader() },
    body: form,
  })
  if (!res.ok) throw new Error(await parseError(res))
  return await res.json()
}

export async function fetchDocuments(): Promise<any[]> {
  const res = await fetch(`${API_BASE}/api/documents`, {
    method: 'GET',
    headers: { ...getAuthHeader() },
  })
  if (!res.ok) throw new Error(await parseError(res))
  return (await res.json()) as any[]
}

export async function updateDocumentAccess(id: string, accessList: string[]): Promise<any> {
  const res = await fetch(`${API_BASE}/api/documents/${id}/access`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeader()
    },
    body: JSON.stringify({ access_list: accessList }),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return await res.json()
}

export async function removeDocument(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/documents/${id}`, {
    method: 'DELETE',
    headers: { ...getAuthHeader() },
  })
  if (!res.ok) throw new Error(await parseError(res))
}

