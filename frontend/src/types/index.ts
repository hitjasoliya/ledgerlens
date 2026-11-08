export type Role = 'admin' | 'employee'

export type User = {
  id: string
  username: string
  password?: string
  role: Role
  createdAt: number
  createdBy?: string
}

export type SafeUser = Omit<User, 'password'>

export type DocumentStatus =
  | 'queued'
  | 'processing'
  | 'searchable'
  | 'failed'
  | 'deleting'
  | 'cleanup_pending'

export type JobStatus =
  | 'queued'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'cleanup_pending'

export type Citation = {
  document_id: string
  filename: string
  page: number
  chunk_id: string
  source_url: string
}

export type DocumentResponse = {
  id: string
  filename: string
  source: string
  uploaded_by_id: string
  uploaded_by: string
  owner_id: string | null
  uploaded_at: number
  access_list: string[]
  pages_parsed: number
  chunks_created: number
  chunks_indexed: number
  status: DocumentStatus
  parser?: string | null
  embedding_model?: string | null
  embedding_dims?: number | null
  error_message?: string | null
}

export type FileEntry = {
  id: string
  filename: string
  source: string
  uploadedBy: string
  uploadedById: string
  ownerId: string | null
  uploadedAt: number
  accessList: string[]
  pagesParsed: number
  chunksCreated: number
  chunksIndexed: number
  status: DocumentStatus
  parser?: string | null
  embeddingModel?: string | null
  embeddingDims?: number | null
  errorMessage?: string | null
}

export type ChatMessageResponse = {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  chunks_used?: number
  unavailable?: boolean
  created_at: number
}

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  chunksUsed?: number
  unavailable?: boolean
  createdAt: number
  timestamp: number
  attachedFile?: { name: string; fileId?: string }
}

export type ChatSessionResponse = {
  id: string
  title: string
  user_id: string
  created_at: number
  updated_at: number
  selected_document_ids: string[]
  revision: number
  messages: ChatMessageResponse[]
}

/** A chat as listed in the sidebar; load the chat itself for its messages. */
export type ChatSessionSummaryResponse = {
  id: string
  title: string
  created_at: number
  updated_at: number
  selected_document_ids: string[]
  message_count: number
}

/** One page of a list endpoint. */
export type Page<T> = {
  items: T[]
  total: number
  limit: number
  offset: number
}

export type ChatSession = {
  id: string
  title: string
  userId: string
  createdAt: number
  updatedAt: number
  selectedDocumentIds: string[]
  revision: number
  messages: ChatMessage[]
}

export type ChatResponse = {
  answer: string
  citations: Citation[]
  chunks_used: number
  message_id?: string
  user_message_id?: string
}

export type IngestResponse = {
  id: string
  job_id: string
  source: string
  pages_parsed: number
  chunks_created: number
  chunks_indexed: number
}

export type JobStatusResponse = {
  job_id: string
  status: JobStatus
  stage: string
  error_message?: string | null
  pages_parsed: number
  chunks_created: number
  chunks_indexed: number
  document_id?: string | null
}


export type ClearEmbeddingsResponse = {
  ok: boolean
  deleted: number
  files_deleted: number
  cleanup_pending?: number
}

