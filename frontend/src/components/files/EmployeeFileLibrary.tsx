import { useMemo, useRef, useState } from 'react'
import type { FileEntry, SafeUser } from '../../types'
import { Button } from '../ui/Button'
import { UploadIcon } from '../ui/Icon'
import { FileTable } from './FileTable'
import {
  DELETE_CONFIRMATION,
  deleteFile,
  describeDeletionError,
  retryFile,
  pollJobUntilDone,
} from '../../services/fileService'
import { useAccessibleFilesState, useOwnFilesState } from '../../services/hooks'
import { MAX_UPLOAD_BYTES, MAX_UPLOAD_PAGES, ingestPdf } from '../../lib/api'
import { bus, Topics } from '../../lib/eventBus'

type Props = {
  user: SafeUser
}

export function EmployeeFileLibrary({ user }: Props) {
  const {
    files: sharedFiles,
    loading: sharedLoading,
    error: sharedError,
    reload: reloadShared,
  } = useAccessibleFilesState(user.id)

  const {
    files: ownFiles,
    loading: ownLoading,
    error: ownError,
    reload: reloadOwn,
  } = useOwnFilesState(user.id)

  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleUpload = async (file: File | null) => {
    if (!file) return
    setError(null)
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setError('Only PDF files are supported')
      return
    }

    setUploading(true)
    try {
      // POST multipart accepts file ONLY per contract
      const result = await ingestPdf(file)
      bus.emit(Topics.files)

      if (result.job_id) {
        void pollJobUntilDone(result.job_id).catch((err: unknown) => {
          setError(err instanceof Error ? err.message : String(err))
        })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const handleRetry = (file: FileEntry) => {
    setError(null)
    void retryFile(file.id).catch((err: unknown) => {
      setError(err instanceof Error ? err.message : String(err))
    })
  }

  const handleDelete = async (file: FileEntry) => {
    const confirmed = confirm(
      `Permanently delete "${file.filename}", including for anyone it was shared with? ${DELETE_CONFIRMATION}`,
    )
    if (!confirmed) return

    setError(null)
    setDeletingId(file.id)
    try {
      await deleteFile(file.id)
    } catch (err) {
      setError(describeDeletionError('Document deletion', err))
    } finally {
      setDeletingId(null)
    }
  }

  // Files shared with employee (uploaded by admin/others)
  const sharedWithMe = useMemo(
    () => sharedFiles.filter((f) => f.uploadedById !== user.id),
    [sharedFiles, user.id],
  )

  // Files uploaded by this employee
  const uploadedByMe = useMemo(
    () => ownFiles.filter((f) => f.uploadedById === user.id),
    [ownFiles, user.id],
  )

  return (
    <div className="page">
      <div className="page__inner">
        <header className="page__header">
          <div>
            <h1 className="page__title">Documents</h1>
            <p className="page__subtitle">
              Your private PDFs and the documents an administrator shared with you. Uploads can be up
              to {MAX_UPLOAD_PAGES} pages and {MAX_UPLOAD_BYTES / 1024 / 1024} MB.
            </p>
          </div>
          <div className="page__actions">
            <input
              ref={fileRef}
              type="file"
              accept="application/pdf"
              hidden
              onChange={(e) => void handleUpload(e.target.files?.[0] ?? null)}
            />
            <Button
              variant="primary"
              leftIcon={<UploadIcon size={15} />}
              onClick={() => fileRef.current?.click()}
              loading={uploading}
            >
              Upload PDF
            </Button>
          </div>
        </header>

        {error && (
          <div className="notice notice--danger" role="alert">
            {error}
          </div>
        )}

        <section className="page__section">
          <h2 className="page__section-title">Your documents</h2>
          {ownError ? (
            <div className="notice notice--danger" role="alert">
              <span>Couldn’t load your documents: {ownError}</span>
              <Button size="sm" variant="secondary" onClick={reloadOwn}>
                Retry
              </Button>
            </div>
          ) : ownLoading && uploadedByMe.length === 0 ? (
            <div className="loading-state">Loading your documents…</div>
          ) : (
            <FileTable
              files={uploadedByMe}
              columns={['pages', 'date']}
              onDelete={handleDelete}
            onRetry={handleRetry}
              deletingId={deletingId}
              emptyTitle="No documents yet"
              emptyDescription="Upload a PDF. Only you can ask questions about it."
            />
          )}
        </section>

        <section className="page__section">
          <h2 className="page__section-title">Shared with you</h2>
          {sharedError ? (
            <div className="notice notice--danger" role="alert">
              <span>Couldn’t load shared documents: {sharedError}</span>
              <Button size="sm" variant="secondary" onClick={reloadShared}>
                Retry
              </Button>
            </div>
          ) : sharedLoading && sharedWithMe.length === 0 ? (
            <div className="loading-state">Loading shared documents…</div>
          ) : (
            <FileTable
              files={sharedWithMe}
              columns={['owner', 'pages', 'date']}
              emptyTitle="Nothing shared yet"
              emptyDescription="Documents an administrator shares with you appear here."
            />
          )}
        </section>
      </div>
    </div>
  )
}
