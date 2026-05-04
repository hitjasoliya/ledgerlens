import type { FileEntry, FileScope } from '../types'
import { uid } from '../lib/ids'
import { readJSON, StorageKeys, writeJSON } from '../lib/storage'
import { bus, Topics } from '../lib/eventBus'

export type CreateFileInput = {
  filename: string
  source: string
  uploadedBy: string
  uploadedById: string
  scope: FileScope
  accessList: string[]
  pagesParsed: number
  chunksCreated: number
  chunksIndexed: number
  isPersistent: boolean
  sessionId: string
}

function readAll(): FileEntry[] {
  return readJSON<FileEntry[]>(StorageKeys.files, [])
}

function writeAll(files: FileEntry[]): void {
  writeJSON(StorageKeys.files, files)
}

export function listAllFiles(): FileEntry[] {
  return readAll().sort((a, b) => b.uploadedAt - a.uploadedAt)
}

export function listAdminFiles(): FileEntry[] {
  return listAllFiles().filter((f) => f.scope === 'admin')
}

export function listFilesAccessibleTo(userId: string): FileEntry[] {
  return listAllFiles().filter(
    (f) =>
      f.scope === 'admin' &&
      (f.accessList.includes(userId) || f.uploadedById === userId),
  )
}

export function listFilesOwnedBy(userId: string): FileEntry[] {
  return listAllFiles().filter(
    (f) => f.scope === 'employee' && f.uploadedById === userId,
  )
}

export function findFile(id: string): FileEntry | null {
  return readAll().find((f) => f.id === id) ?? null
}

export function createFile(input: CreateFileInput): FileEntry {
  const entry: FileEntry = {
    ...input,
    id: uid('file'),
    uploadedAt: Date.now(),
  }
  writeAll([entry, ...readAll()])
  bus.emit(Topics.files)
  return entry
}

export function updateFileAccess(id: string, accessList: string[]): FileEntry | null {
  const files = readAll()
  const idx = files.findIndex((f) => f.id === id)
  if (idx === -1) return null
  const updated: FileEntry = { ...files[idx], accessList }
  files[idx] = updated
  writeAll(files)
  bus.emit(Topics.files)
  return updated
}

export function deleteFile(id: string): void {
  writeAll(readAll().filter((f) => f.id !== id))
  bus.emit(Topics.files)
}
