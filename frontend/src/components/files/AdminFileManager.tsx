import { useState } from 'react'
import type { FileEntry, SafeUser } from '../../types'
import { Button } from '../ui/Button'
import { PlusIcon } from '../ui/Icon'
import { FileTable } from './FileTable'
import { FileUploadDialog } from './FileUploadDialog'
import { AccessManagerDialog } from './AccessManagerDialog'
import {
  clearAllEmbeddings,
  DELETE_CONFIRMATION,
  deleteFile,
  describeDeletionError,
  retryFile,
} from '../../services/fileService'
import { useAdminFilesState, useEmployees } from '../../services/hooks'

type Props = {
  uploader: SafeUser
}

export function AdminFileManager({ uploader }: Props) {
  const { files, loading, error, reload } = useAdminFilesState()
  const employees = useEmployees()
  const [uploadOpen, setUploadOpen] = useState(false)
  const [accessTarget, setAccessTarget] = useState<FileEntry | null>(null)
  const [clearing, setClearing] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const handleRetry = (file: FileEntry) => {
    setActionError(null)
    void retryFile(file.id).catch((err: unknown) => {
      setActionError(err instanceof Error ? err.message : String(err))
    })
  }

  const handleDelete = async (file: FileEntry) => {
    const confirmed = confirm(
      `Permanently delete "${file.filename}" for its owner and every recipient? ${DELETE_CONFIRMATION}`,
    )
    if (!confirmed) return

    setActionError(null)
    setDeletingId(file.id)
    try {
      await deleteFile(file.id)
    } catch (err) {
      setActionError(describeDeletionError('Document deletion', err))
    } finally {
      setDeletingId(null)
    }
  }

  const handleClearEmbeddings = async () => {
    const confirmed = confirm(
      'Permanently delete ALL managed documents, their indexed chunks, and their uploaded PDFs? This cannot be undone, and every conversation that selected them will stop answering document questions. Continue?',
    )
    if (!confirmed) return

    setClearing(true)
    setActionError(null)
    try {
      const res = await clearAllEmbeddings()
      alert(`Cleared ${res.deleted} chunk(s) and deleted ${res.files_deleted} file(s).`)
    } catch (err) {
      setActionError(describeDeletionError('Store wipe', err))
    } finally {
      setClearing(false)
    }
  }

  return (
    <div className="page">
      <div className="page__inner">
        <header className="page__header">
          <div>
            <h1 className="page__title">Documents</h1>
            <p className="page__subtitle">
              Upload PDFs and choose which employees can ask questions about them.
            </p>
          </div>
          <div className="page__actions">
            <Button
              variant="danger"
              onClick={handleClearEmbeddings}
              disabled={clearing || files.length === 0}
            >
              {clearing ? 'Deleting…' : 'Delete all'}
            </Button>
            <Button
              variant="primary"
              leftIcon={<PlusIcon size={15} />}
              onClick={() => setUploadOpen(true)}
            >
              Upload PDF
            </Button>
          </div>
        </header>

        {actionError && (
          <div className="notice notice--danger" role="alert">
            {actionError}
          </div>
        )}

        {error ? (
          <div className="notice notice--danger" role="alert">
            <span>Couldn’t load documents: {error}</span>
            <Button variant="secondary" size="sm" onClick={reload}>
              Retry
            </Button>
          </div>
        ) : loading && files.length === 0 ? (
          <div className="loading-state">Loading documents…</div>
        ) : (
          <FileTable
            files={files}
            employees={employees}
            onManageAccess={(f) => setAccessTarget(f)}
            onDelete={handleDelete}
            onRetry={handleRetry}
            deletingId={deletingId}
            emptyTitle="No documents yet"
            emptyDescription="Upload a PDF to start asking questions about it."
          />
        )}
      </div>

      <FileUploadDialog
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        uploader={uploader}
        employees={employees}
      />

      <AccessManagerDialog
        open={!!accessTarget}
        file={accessTarget}
        employees={employees}
        onClose={() => setAccessTarget(null)}
      />
    </div>
  )
}
