import type {
  ChatResponse,
  ChatSessionResponse,
  ChatSessionSummaryResponse,
  ClearEmbeddingsResponse,
  DocumentResponse,
  IngestResponse,
  JobStatusResponse,
  Page,
  Role,
  SafeUser,
} from '../types'

export const API_BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function formatErrorDetail(item: unknown): string {
  if (typeof item === 'string') return item
  if (item && typeof item === 'object') {
    const errObj = item as Record<string, unknown>
    if (typeof errObj.msg === 'string') {
      const cleanMsg = errObj.msg.replace(/^Value error,\s*/, '')
      if (Array.isArray(errObj.loc) && errObj.loc.length > 0) {
        const field = errObj.loc
          .filter((p) => p !== 'body' && p !== 'query' && p !== 'path')
          .join('.')
        return field ? `${field}: ${cleanMsg}` : cleanMsg
      }
      return cleanMsg
    }
    if (typeof errObj.message === 'string') return errObj.message
    if (typeof errObj.detail === 'string') return errObj.detail
    try {
      return JSON.stringify(errObj)
    } catch {
      return String(errObj)
    }
  }
  return String(item)
}

async function parseError(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: unknown; message?: unknown; error?: unknown }
    if (typeof data.detail === 'string') return data.detail
    if (Array.isArray(data.detail)) {
      return data.detail.map(formatErrorDetail).join(', ')
    }
    if (data.detail && typeof data.detail === 'object') {
      return formatErrorDetail(data.detail)
    }
    if (typeof data.message === 'string') return data.message
    if (typeof data.error === 'string') return data.error
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

export async function authenticatedFetch(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  const headers = {
    ...getAuthHeader(),
    ...(init?.headers ?? {}),
  }
  const res = await fetch(url, { ...init, headers })
  if (res.status === 401) {
    // Authorized credentials rejected: purge local credentials and notify
    try {
      localStorage.removeItem('ledgerlens.session')
    } catch {
      // ignore
    }
    window.dispatchEvent(new Event('ledgerlens:unauthorized'))
  }
  return res
}

const PAGE_LIMIT = 200

/** Read every page of a paged list endpoint. */
async function fetchAll<T>(path: string, signal?: AbortSignal): Promise<T[]> {
  const items: T[] = []
  for (let offset = 0; ; offset += PAGE_LIMIT) {
    const res = await authenticatedFetch(`${API_BASE}${path}?limit=${PAGE_LIMIT}&offset=${offset}`, {
      method: 'GET',
      signal,
    })
    if (!res.ok) throw new ApiError(res.status, await parseError(res))
    const page = (await res.json()) as Page<T>
    items.push(...page.items)
    if (page.items.length === 0 || items.length >= page.total) return items
  }
}

const chatUrl = (sessionId: string, suffix = '') =>
  `${API_BASE}/api/chat/sessions/${encodeURIComponent(sessionId)}${suffix}`

// ---------------------------------------------------------------------------
// Chat API
// ---------------------------------------------------------------------------

export async function sendMessage(
  message: string,
  sessionId: string,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const res = await authenticatedFetch(chatUrl(sessionId, '/messages'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
    signal,
  })
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
  return (await res.json()) as ChatResponse
}

export function fetchChatSessions(signal?: AbortSignal): Promise<ChatSessionSummaryResponse[]> {
  return fetchAll<ChatSessionSummaryResponse>('/api/chat/sessions', signal)
}

export async function fetchChatSession(
  id: string,
  signal?: AbortSignal,
): Promise<ChatSessionResponse> {
  const res = await authenticatedFetch(
    `${API_BASE}/api/chat/sessions/${encodeURIComponent(id)}`,
    {
      method: 'GET',
      signal,
    },
  )
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
  return (await res.json()) as ChatSessionResponse
}

export async function createChatSession(
  data: {
    title?: string
    /** A chat's documents are chosen here, once; at least one is required. */
    selected_document_ids: string[]
  },
  signal?: AbortSignal,
): Promise<ChatSessionResponse> {
  const res = await authenticatedFetch(`${API_BASE}/api/chat/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: data.title ?? 'New chat',
      selected_document_ids: data.selected_document_ids,
    }),
    signal,
  })
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
  return (await res.json()) as ChatSessionResponse
}

export async function regenerateChatMessage(
  sessionId: string,
  messageId: string,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const res = await authenticatedFetch(
    `${API_BASE}/api/chat/sessions/${encodeURIComponent(sessionId)}/regenerate`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message_id: messageId }),
      signal,
    },
  )
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
  return (await res.json()) as ChatResponse
}

export async function clearConversation(sessionId: string, signal?: AbortSignal): Promise<void> {
  const res = await authenticatedFetch(chatUrl(sessionId, '/messages'), { method: 'DELETE', signal })
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
}

export async function deleteConversation(sessionId: string, signal?: AbortSignal): Promise<void> {
  const res = await authenticatedFetch(chatUrl(sessionId), { method: 'DELETE', signal })
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
}

// ---------------------------------------------------------------------------
// Ingest & Documents API
// ---------------------------------------------------------------------------

// Mirrors the server defaults; the server enforces both limits regardless.
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024
export const MAX_UPLOAD_PAGES = 40

export async function ingestPdf(file: File, signal?: AbortSignal): Promise<IngestResponse> {
  if (file.size > MAX_UPLOAD_BYTES) {
    throw new Error(`PDF is larger than ${MAX_UPLOAD_BYTES / 1024 / 1024} MB.`)
  }

  const form = new FormData()
  form.append('file', file)

  const res = await authenticatedFetch(`${API_BASE}/api/documents`, {
    method: 'POST',
    body: form,
    signal,
  })
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
  return (await res.json()) as IngestResponse
}

export async function getJobStatus(
  jobId: string,
  signal?: AbortSignal,
): Promise<JobStatusResponse> {
  const res = await authenticatedFetch(
    `${API_BASE}/api/jobs/${encodeURIComponent(jobId)}`,
    {
      method: 'GET',
      signal,
    },
  )
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
  return (await res.json()) as JobStatusResponse
}

export function fetchDocuments(signal?: AbortSignal): Promise<DocumentResponse[]> {
  return fetchAll<DocumentResponse>('/api/documents', signal)
}

/** Parse a document again, e.g. after a failure. Owners and admins only. */
export async function reindexDocument(id: string, signal?: AbortSignal): Promise<IngestResponse> {
  const res = await authenticatedFetch(
    `${API_BASE}/api/documents/${encodeURIComponent(id)}/reindex`,
    { method: 'POST', signal },
  )
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
  return (await res.json()) as IngestResponse
}

export async function updateDocumentAccess(
  id: string,
  accessList: string[],
  signal?: AbortSignal,
): Promise<DocumentResponse> {
  const res = await authenticatedFetch(
    `${API_BASE}/api/documents/${encodeURIComponent(id)}/access`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ access_list: accessList }),
      signal,
    },
  )
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
  return (await res.json()) as DocumentResponse
}

export async function removeDocument(id: string, signal?: AbortSignal): Promise<void> {
  const res = await authenticatedFetch(
    `${API_BASE}/api/documents/${encodeURIComponent(id)}`,
    {
      method: 'DELETE',
      signal,
    },
  )
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
}

export async function clearAllEmbeddings(signal?: AbortSignal): Promise<ClearEmbeddingsResponse> {
  const res = await authenticatedFetch(`${API_BASE}/api/documents`, {
    method: 'DELETE',
    signal,
  })
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
  return (await res.json()) as ClearEmbeddingsResponse
}

export async function fetchDocumentSourceBlob(
  documentId: string,
  signal?: AbortSignal,
): Promise<Blob> {
  const res = await authenticatedFetch(
    `${API_BASE}/api/documents/${encodeURIComponent(documentId)}/source`,
    {
      method: 'GET',
      signal,
    },
  )
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
  return await res.blob()
}

// ---------------------------------------------------------------------------
// Auth & Users API
// ---------------------------------------------------------------------------

export type LoginResponse = {
  access_token: string
  token_type?: string
  user: SafeUser
}

export type UserCreateInput = {
  username: string
  password: string
  role: Role
}

export async function loginUser(
  username: string,
  password: string,
): Promise<LoginResponse> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    throw new Error(`Login failed due to network error: ${msg}`, { cause: err })
  }
  if (!res.ok) {
    const errorMsg = await parseError(res)
    throw new ApiError(res.status, errorMsg)
  }
  return (await res.json()) as LoginResponse
}

export async function logoutUser(): Promise<void> {
  let res: Response
  try {
    res = await authenticatedFetch(`${API_BASE}/api/auth/logout`, {
      method: 'POST',
    })
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    throw new Error(`Logout failed due to network error: ${msg}`, { cause: err })
  }
  if (!res.ok) {
    const errorMsg = await parseError(res)
    throw new ApiError(res.status, errorMsg)
  }
}

export async function getProfile(): Promise<SafeUser> {
  let res: Response
  try {
    res = await authenticatedFetch(`${API_BASE}/api/auth/me`, {
      method: 'GET',
    })
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    throw new Error(`Failed to restore profile due to network error: ${msg}`, { cause: err })
  }
  if (!res.ok) {
    const errorMsg = await parseError(res)
    throw new ApiError(res.status, errorMsg)
  }
  return (await res.json()) as SafeUser
}

export function fetchUsers(signal?: AbortSignal): Promise<SafeUser[]> {
  return fetchAll<SafeUser>('/api/users', signal)
}

export async function saveUser(input: UserCreateInput, signal?: AbortSignal): Promise<SafeUser> {
  const res = await authenticatedFetch(`${API_BASE}/api/users`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
    signal,
  })
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
  return (await res.json()) as SafeUser
}

export async function removeUser(
  userId: string,
  transferTo?: string,
  signal?: AbortSignal,
): Promise<void> {
  const query = transferTo ? `?transfer_to=${encodeURIComponent(transferTo)}` : ''
  const res = await authenticatedFetch(
    `${API_BASE}/api/users/${encodeURIComponent(userId)}${query}`,
    {
      method: 'DELETE',
      signal,
    },
  )
  if (!res.ok) throw new ApiError(res.status, await parseError(res))
}

export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`)
    return res.ok
  } catch {
    return false
  }
}
