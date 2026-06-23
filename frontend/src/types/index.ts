export type Role = 'admin' | 'employee'

export type User = {
  id: string
  username: string
  password: string
  role: Role
  createdAt: number
  createdBy?: string
}

export type SafeUser = Omit<User, 'password'>

export type FileScope = 'admin' | 'employee'

export type FileEntry = {
  id: string
  filename: string
  source: string
  uploadedBy: string
  uploadedById: string
  uploadedAt: number
  scope: FileScope
  accessList: string[]
  pagesParsed: number
  chunksCreated: number
  chunksIndexed: number
  isPersistent: boolean
  sessionId: string
}

export type Citation = {
  page: number
  chunk_id: string
}

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  chunksUsed?: number
  attachedFile?: { name: string; fileId?: string }
  timestamp: number
}

export type ChatSession = {
  id: string
  title: string
  ownerId: string
  createdAt: number
  updatedAt: number
  messages: ChatMessage[]
  contextFileId?: string
}

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
  id?: string
}
