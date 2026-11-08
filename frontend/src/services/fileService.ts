import type { ClearEmbeddingsResponse, DocumentResponse, FileEntry } from '../types'
import {
  ApiError,
  clearAllEmbeddings as apiClearAllEmbeddings,
  fetchDocuments,
  getJobStatus,
  reindexDocument,
  removeDocument,
  updateDocumentAccess,
} from '../lib/api'
import { bus, Topics } from '../lib/eventBus'

export function mapDocument(doc: DocumentResponse): FileEntry {
  return {
    id: doc.id,
    filename: doc.filename,
    source: doc.source,
    uploadedBy: doc.uploaded_by,
    uploadedById: doc.uploaded_by_id,
    ownerId: doc.owner_id ?? null,
    uploadedAt: doc.uploaded_at,
    accessList: doc.access_list ?? [],
    pagesParsed: doc.pages_parsed,
    chunksCreated: doc.chunks_created,
    chunksIndexed: doc.chunks_indexed,
    status: doc.status,
    parser: doc.parser,
    embeddingModel: doc.embedding_model,
    embeddingDims: doc.embedding_dims,
    errorMessage: doc.error_message,
  }
}

export async function listAllFiles(): Promise<FileEntry[]> {
  const docs = await fetchDocuments()
  return docs.map(mapDocument).sort((a, b) => b.uploadedAt - a.uploadedAt)
}

export async function listAdminFiles(): Promise<FileEntry[]> {
  return await listAllFiles()
}

export async function listFilesAccessibleTo(userId: string): Promise<FileEntry[]> {
  const all = await listAllFiles()
  return all.filter(
    (f) =>
      f.accessList.includes(userId) ||
      f.ownerId === userId,
  )
}

export async function listFilesOwnedBy(userId: string): Promise<FileEntry[]> {
  const all = await listAllFiles()
  return all.filter((f) => f.ownerId === userId)
}

export async function updateFileAccess(
  id: string,
  accessList: string[],
): Promise<FileEntry> {
  const updated = await updateDocumentAccess(id, accessList)
  bus.emit(Topics.files)
  return mapDocument(updated)
}

// Deletion and wipe refresh the library whatever the outcome: a pending cleanup
// has already withdrawn access, so the stale row must not linger as if usable.
export async function deleteFile(id: string): Promise<void> {
  try {
    await removeDocument(id)
  } finally {
    bus.emit(Topics.files)
  }
}

export async function clearAllEmbeddings(): Promise<ClearEmbeddingsResponse> {
  try {
    return await apiClearAllEmbeddings()
  } finally {
    bus.emit(Topics.files)
  }
}

/** Queue a failed document for parsing again and follow the new job. */
export async function retryFile(id: string): Promise<void> {
  try {
    const { job_id } = await reindexDocument(id)
    bus.emit(Topics.files)
    await pollJobUntilDone(job_id)
  } finally {
    bus.emit(Topics.files)
  }
}

export const DELETE_CONFIRMATION =
  'This is irreversible. Conversations that selected this document will stop answering document questions and must start a new conversation.'

export function describeDeletionError(action: string, err: unknown): string {
  const message = err instanceof Error ? err.message : String(err)
  if (err instanceof ApiError && err.status === 503) {
    return `${action} incomplete: ${message}. The library now shows the current state; cleanup retries automatically once storage and search recover.`
  }
  return `${action} failed: ${message}`
}

function delay(ms: number): Promise<void> {
  const { promise, resolve } = Promise.withResolvers<void>()
  setTimeout(resolve, ms)
  return promise
}

export async function pollJobUntilDone(
  jobId: string,
  timeoutMs = 5 * 60 * 1000,
): Promise<string> {
  const deadline = Date.now() + timeoutMs
  try {
    while (Date.now() < deadline) {
      const job = await getJobStatus(jobId)
      if (job.status === 'completed' || job.status === 'failed') return job.status
      if (job.status === 'cleanup_pending') throw new Error('Upload is pending cleanup')
      await delay(1500)
    }
    throw new Error('Ingestion is still pending. The accepted upload remains in your library.')
  } finally {
    bus.emit(Topics.files)
  }
}

export async function waitForDocumentsSearchable(
  documentIds: string[],
  timeoutMs = 5 * 60 * 1000,
): Promise<void> {
  if (documentIds.length === 0) return
  const idSet = new Set(documentIds)
  const deadline = Date.now() + timeoutMs

  while (Date.now() < deadline) {
    const files = await listAllFiles()
    const targetFiles = files.filter((f) => idSet.has(f.id))
    if (targetFiles.length !== idSet.size) {
      throw new Error('A selected source is unavailable. Restore access or start a new conversation.')
    }

    // Check if any failed
    const failedDoc = targetFiles.find((f) => f.status === 'failed')
    if (failedDoc) {
      throw new Error(
        `Selected document "${failedDoc.filename}" failed processing: ${
          failedDoc.errorMessage || 'Unknown error'
        }`,
      )
    }

    // Check if any deleting or cleanup_pending
    const unavailableDoc = targetFiles.find(
      (f) => f.status === 'deleting' || f.status === 'cleanup_pending',
    )
    if (unavailableDoc) {
      throw new Error(
        `Selected document "${unavailableDoc.filename}" is unavailable (${unavailableDoc.status}).`,
      )
    }

    // All must be searchable
    const allSearchable =
      targetFiles.length === idSet.size &&
      targetFiles.every((f) => f.status === 'searchable')

    if (allSearchable) {
      return
    }

    await delay(1500)
  }

  throw new Error('Timed out waiting for selected documents to become searchable.')
}
