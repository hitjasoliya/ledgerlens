import { useRef, useState } from 'react'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { UploadIcon, FileIcon, CloseIcon } from '../ui/Icon'
import type { SafeUser } from '../../types'
import { ingestPdf } from '../../lib/api'
import { createFile } from '../../services/fileService'
import './FileUploadDialog.css'

type Props = {
  open: boolean
  onClose: () => void
  uploader: SafeUser
  employees: SafeUser[]
}

export function FileUploadDialog({ open, onClose, uploader, employees }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [accessIds, setAccessIds] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dragActive, setDragActive] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const reset = () => {
    setFile(null)
    setAccessIds([])
    setError(null)
    setSubmitting(false)
  }

  const handleClose = () => {
    if (submitting) return
    reset()
    onClose()
  }

  const handleFile = (f: File | null) => {
    if (!f) return
    if (!f.name.toLowerCase().endsWith('.pdf')) {
      setError('Only PDF files are supported')
      return
    }
    setError(null)
    setFile(f)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragActive(false)
    handleFile(e.dataTransfer.files[0] ?? null)
  }

  const toggleAccess = (id: string) => {
    setAccessIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }

  const handleUpload = async () => {
    if (!file) return
    setSubmitting(true)
    setError(null)
    try {
      const result = await ingestPdf({
        file,
        userId: uploader.id,
        sessionId: `admin_persistent_${uploader.id}`,
        isPersistent: true,
        allowedUsers: accessIds,
      })
      createFile({
        filename: file.name,
        source: result.source,
        uploadedBy: uploader.username,
        uploadedById: uploader.id,
        scope: 'admin',
        accessList: accessIds,
        pagesParsed: result.pages_parsed,
        chunksCreated: result.chunks_created,
        chunksIndexed: result.chunks_indexed,
        isPersistent: true,
        sessionId: `admin_persistent_${uploader.id}`,
      })
      reset()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Upload document"
      description="Upload a PDF and choose which employees can access it."
      size="md"
      footer={
        <>
          <Button variant="secondary" onClick={handleClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleUpload}
            loading={submitting}
            disabled={!file}
          >
            Upload & index
          </Button>
        </>
      }
    >
      <div className="upload-dialog">
        <div
          className={`upload-dialog__dropzone ${dragActive ? 'is-active' : ''} ${file ? 'has-file' : ''}`}
          onDragOver={(e) => {
            e.preventDefault()
            setDragActive(true)
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
          role="button"
          tabIndex={0}
        >
          <input
            ref={fileRef}
            type="file"
            accept="application/pdf"
            hidden
            onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
          />
          {file ? (
            <div className="upload-dialog__file">
              <FileIcon size={18} />
              <span>{file.name}</span>
              <button
                type="button"
                className="upload-dialog__file-clear"
                onClick={(e) => {
                  e.stopPropagation()
                  setFile(null)
                  if (fileRef.current) fileRef.current.value = ''
                }}
              >
                <CloseIcon size={14} />
              </button>
            </div>
          ) : (
            <div className="upload-dialog__placeholder">
              <UploadIcon size={20} />
              <span>Drop PDF here or click to browse</span>
            </div>
          )}
        </div>

        {error && <div className="upload-dialog__error">{error}</div>}

        <div className="upload-dialog__access">
          <div className="upload-dialog__access-header">
            <h4>Grant access to employees</h4>
            <span className="upload-dialog__access-count">
              {accessIds.length} selected
            </span>
          </div>
          {employees.length === 0 ? (
            <div className="upload-dialog__no-employees">
              No employees yet. Create one from the Users tab to assign access.
            </div>
          ) : (
            <div className="upload-dialog__employee-list">
              {employees.map((emp) => {
                const checked = accessIds.includes(emp.id)
                return (
                  <label
                    key={emp.id}
                    className={`upload-dialog__employee ${checked ? 'is-checked' : ''}`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleAccess(emp.id)}
                    />
                    <span className="upload-dialog__employee-name">
                      {emp.username}
                    </span>
                  </label>
                )
              })}
            </div>
          )}
          <p className="upload-dialog__hint">
            Leave empty to keep this file visible only to admins.
          </p>
        </div>
      </div>
    </Modal>
  )
}
