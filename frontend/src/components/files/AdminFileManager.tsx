import { useState } from 'react'
import type { FileEntry, SafeUser } from '../../types'
import { Button } from '../ui/Button'
import { PlusIcon } from '../ui/Icon'
import { FileTable } from './FileTable'
import { FileUploadDialog } from './FileUploadDialog'
import { AccessManagerDialog } from './AccessManagerDialog'
import { clearAllEmbeddings, deleteFile } from '../../services/fileService'
import { useAdminFiles, useEmployees } from '../../services/hooks'
import './AdminFileManager.css'

type Props = {
  uploader: SafeUser
}

export function AdminFileManager({ uploader }: Props) {
  const files = useAdminFiles()
  const employees = useEmployees()
  const [uploadOpen, setUploadOpen] = useState(false)
  const [accessTarget, setAccessTarget] = useState<FileEntry | null>(null)
  const [clearing, setClearing] = useState(false)

  const handleDelete = (file: FileEntry) => {
    if (!confirm(`Delete "${file.filename}" from the library? This also removes its indexed chunks from the backend.`)) return
    deleteFile(file.id)
  }

  const handleClearEmbeddings = async () => {
    if (!confirm('This permanently deletes ALL indexed chunks, uploaded PDF files, and document records from the backend. This cannot be undone. Continue?')) return
    setClearing(true)
    try {
      const { deleted, filesDeleted } = await clearAllEmbeddings()
      alert(`Cleared ${deleted} chunk(s) and deleted ${filesDeleted} file(s).`)
    } catch (err) {
      alert(`Failed to clear embeddings: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setClearing(false)
    }
  }

  return (
    <div className="admin-files">
      <header className="admin-files__header">
        <div>
          <h2 className="admin-files__title">Document library</h2>
          <p className="admin-files__subtitle">
            Upload PDFs, then choose which employees can query them in chat.
          </p>
        </div>
        <div className="admin-files__actions">
          <Button
            variant="danger"
            onClick={handleClearEmbeddings}
            disabled={clearing || files.length === 0}
          >
            {clearing ? 'Clearing…' : 'Clear embeddings'}
          </Button>
          <Button
            variant="primary"
            leftIcon={<PlusIcon size={14} />}
            onClick={() => setUploadOpen(true)}
          >
            Upload PDF
          </Button>
        </div>
      </header>

      <FileTable
        files={files}
        employees={employees}
        onManageAccess={(f) => setAccessTarget(f)}
        onDelete={handleDelete}
        emptyTitle="No documents yet"
        emptyDescription="Upload your first PDF to start grounding answers in your enterprise data."
      />

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
