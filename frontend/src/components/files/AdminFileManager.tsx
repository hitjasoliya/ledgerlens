import { useState } from 'react'
import type { FileEntry, SafeUser } from '../../types'
import { Button } from '../ui/Button'
import { PlusIcon } from '../ui/Icon'
import { FileTable } from './FileTable'
import { FileUploadDialog } from './FileUploadDialog'
import { AccessManagerDialog } from './AccessManagerDialog'
import { deleteFile } from '../../services/fileService'
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

  const handleDelete = (file: FileEntry) => {
    if (!confirm(`Delete "${file.filename}" from the library? Indexed chunks remain in the backend.`)) return
    deleteFile(file.id)
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
        <Button
          variant="primary"
          leftIcon={<PlusIcon size={14} />}
          onClick={() => setUploadOpen(true)}
        >
          Upload PDF
        </Button>
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
