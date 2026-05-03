export type Citation = { page: number; chunk_id: string }

export type ChatResponse = {
  answer: string
  citations: Citation[]
  chunks_used: number
}

export type IngestResponse = {
  source: string
  pages_parsed: number
  chunks_created: number
  chunks_indexed: number
}

export type Message = {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  chunks_used?: number
  timestamp: Date
}
