import type { ChatResponse, IngestResponse } from './types'

const apiBase = import.meta.env.VITE_API_URL ?? ''

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

export async function sendMessage(message: string): Promise<ChatResponse> {
  const res = await fetch(`${apiBase}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return (await res.json()) as ChatResponse
}

export async function clearConversation(): Promise<void> {
  const res = await fetch(`${apiBase}/api/chat/clear`, { method: 'POST' })
  if (!res.ok) throw new Error(await parseError(res))
}

export async function ingestPdf(file: File): Promise<IngestResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${apiBase}/api/ingest`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) throw new Error(await parseError(res))
  return (await res.json()) as IngestResponse
}
