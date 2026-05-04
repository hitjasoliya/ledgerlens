import { useRef, useState } from 'react'
import type { FileEntry, SafeUser } from '../../types'
import { Button } from '../ui/Button'
import { UploadIcon } from '../ui/Icon'
import { FileTable } from './FileTable'
import { createFile, deleteFile } from '../../services/fileService'
import { useAccessibleFiles, useOwnFiles } from '../../services/hooks'
import { ingestPdf } from '../../lib/api'
import './EmployeeFileLibrary.css'

type Props = {
  user: SafeUser
}

export function EmployeeFileLibrary({ user }: Props) {
  const shared = useAccessibleFiles(user.id)
  const own = useOwnFiles(user.id)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
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
      const sessionId = `personal_${user.id}`
      const result = await ingestPdf({
        file,
        userId: user.id,
        sessionId,
        isPersistent: true,
        allowedUsers: [user.id],
      })
      createFile({
        filename: file.name,
        source: result.source,
        uploadedBy: user.username,
        uploadedById: user.id,
        scope: 'employee',
        accessList: [user.id],
        pagesParsed: result.pages_parsed,
        chunksCreated: result.chunks_created,
        chunksIndexed: result.chunks_indexed,
        isPersistent: true,
        sessionId,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const handleDelete = (file: FileEntry) => {
    if (!confirm(`Delete "${file.filename}"?`)) return
    deleteFile(file.id)
  }

  const sharedOnly = shared.filter((f) => f.scope === 'admin')

  return (
    <div className="employee-files">
      <section className="employee-files__section">
        <header className="employee-files__header">
          <div>
            <h2 className="employee-files__title">Shared with you</h2>
            <p className="employee-files__subtitle">
              Documents your administrator has granted you access to. Use these as context in chat.
            </p>
          </div>
        </header>
        <FileTable
          files={sharedOnly}
          columns={['owner', 'pages', 'date']}
          emptyTitle="No shared documents yet"
          emptyDescription="Your administrator hasn't granted you access to any files. Reach out to request access."
        />
      </section>

      <section className="employee-files__section">
        <header className="employee-files__header">
          <div>
            <h2 className="employee-files__title">Your personal library</h2>
            <p className="employee-files__subtitle">
              Upload your own PDFs for personal use. They are only visible to you.
            </p>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept="application/pdf"
            hidden
            onChange={(e) => void handleUpload(e.target.files?.[0] ?? null)}
          />
          <Button
            variant="primary"
            leftIcon={<UploadIcon size={14} />}
            onClick={() => fileRef.current?.click()}
            loading={uploading}
          >
            Upload PDF
          </Button>
        </header>

        {error && <div className="employee-files__error">{error}</div>}

        <FileTable
          files={own}
          columns={['pages', 'date']}
          onDelete={handleDelete}
          emptyTitle="No personal files yet"
          emptyDescription="Upload a PDF to keep it private to your account and use it as chat context."
        />
      </section>
    </div>
  )
}
