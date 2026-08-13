import type { FileEntry } from '../types'
import {
  clearAllEmbeddings as apiClearAllEmbeddings,
  fetchDocuments,
  getJobStatus,
  removeDocument,
  updateDocumentAccess,
} from '../lib/api'
import { bus, Topics } from '../lib/eventBus'

function mapDocument(doc: any): FileEntry {
  return {
    id: doc.id,
    filename: doc.filename,
    source: doc.source,
    uploadedBy: doc.uploaded_by,
    uploadedById: doc.uploaded_by_id,
    uploadedAt: doc.uploaded_at,
    scope: doc.scope,
    accessList: doc.access_list,
    pagesParsed: doc.pages_parsed,
    chunksCreated: doc.chunks_created,
    chunksIndexed: doc.chunks_indexed,
    isPersistent: doc.is_persistent,
    sessionId: doc.session_id,
    indexStatus: doc.index_status,
    jobError: doc.job_error,
  }
}

export async function listAllFiles(): Promise<FileEntry[]> {
  try {
    const docs = await fetchDocuments()
    return docs.map(mapDocument).sort((a, b) => b.uploadedAt - a.uploadedAt)
  } catch (e) {
    console.error('Failed to list all files', e)
    return []
  }
}

export async function listAdminFiles(): Promise<FileEntry[]> {
  const all = await listAllFiles()
  return all.filter((f) => f.scope === 'admin')
}

export async function listFilesAccessibleTo(userId: string): Promise<FileEntry[]> {
  const all = await listAllFiles()
  return all.filter(
    (f) =>
      f.scope === 'admin' &&
      (f.accessList.includes(userId) || f.uploadedById === userId),
  )
}

export async function listFilesOwnedBy(userId: string): Promise<FileEntry[]> {
  const all = await listAllFiles()
  return all.filter((f) => f.scope === 'employee' && f.uploadedById === userId)
}

export function findFile(_id: string): FileEntry | null {
  // Note: findFile usage is deprecated in favour of direct accessibleFiles lookup in ChatShell.tsx
  return null
}

export async function createFile(input: any): Promise<FileEntry> {
  // File is automatically created by the backend ingest endpoint.
  // We emit Topics.files to notify hooks to refresh document state.
  bus.emit(Topics.files)
  return {
    id: input.id || '',
    filename: input.filename,
    source: input.source,
    uploadedBy: input.uploadedBy,
    uploadedById: input.uploadedById,
    uploadedAt: Date.now(),
    scope: input.scope,
    accessList: input.accessList,
    pagesParsed: input.pagesParsed,
    chunksCreated: input.chunksCreated,
    chunksIndexed: input.chunksIndexed,
    isPersistent: input.isPersistent,
    sessionId: input.sessionId,
  }
}

export async function updateFileAccess(id: string, accessList: string[]): Promise<FileEntry | null> {
  try {
    const updated = await updateDocumentAccess(id, accessList)
    bus.emit(Topics.files)
    return mapDocument(updated)
  } catch (e) {
    console.error('Failed to update access', e)
    return null
  }
}

export async function deleteFile(id: string): Promise<void> {
  try {
    await removeDocument(id)
    bus.emit(Topics.files)
  } catch (e) {
    console.error('Failed to delete file', e)
  }
}

export async function clearAllEmbeddings(): Promise<{
  deleted: number
  filesDeleted: number
}> {
  const res = await apiClearAllEmbeddings()
  bus.emit(Topics.files)
  return { deleted: res.deleted, filesDeleted: res.files_deleted }
}

export async function pollJobUntilDone(
  jobId: string,
  timeoutMs = 5 * 60 * 1000,
): Promise<string> {
  const deadline = Date.now() + timeoutMs
  let status = 'pending'
  while (Date.now() < deadline) {
    try {
      const job = await getJobStatus(jobId)
      status = job.status
      if (status === 'completed' || status === 'failed') {
        bus.emit(Topics.files)
        return status
      }
    } catch {
      // Job may have been wiped (e.g. "Clear embeddings") while polling; stop quietly.
      bus.emit(Topics.files)
      return status
    }
    const delay = (ms: number): Promise<void> => {
      const { promise, resolve } = Promise.withResolvers<void>()
      setTimeout(resolve, ms)
      return promise
    }
    await delay(2000)
  }
  bus.emit(Topics.files)
  return status
}
