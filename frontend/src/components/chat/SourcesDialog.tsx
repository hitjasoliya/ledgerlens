import { useMemo, useState } from 'react'
import type { FileEntry } from '../../types'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { CheckIcon, FileIcon, UploadIcon } from '../ui/Icon'
import './SourcesDialog.css'

type Props = {
  open: boolean
  files: FileEntry[]
  onConfirm: (selectedDocumentIds: string[]) => Promise<void>
  onClose: () => void
  onGoToDocuments: () => void
}

/** Only searchable documents can start a chat; the rest are shown with the reason. */
const UNAVAILABLE: Partial<Record<FileEntry['status'], string>> = {
  queued: 'Waiting to be indexed',
  processing: 'Indexing…',
  failed: 'Failed to index',
  deleting: 'Being deleted',
  cleanup_pending: 'Being deleted',
}

export function SourcesDialog(props: Props) {
  if (!props.open) return null
  // Remount per open so every new chat starts with a clean selection.
  return <SourcesDialogBody {...props} />
}

function SourcesDialogBody({
  files,
  onConfirm,
  onClose,
  onGoToDocuments,
}: Props) {
  const pickable = useMemo(() => files.filter((f) => !UNAVAILABLE[f.status]), [files])
  const [selected, setSelected] = useState<string[]>([])
  const [query, setQuery] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? files.filter((f) => f.filename.toLowerCase().includes(q)) : files
  }, [files, query])

  const allPicked = pickable.length > 0 && pickable.every((f) => selected.includes(f.id))

  const toggle = (id: string) =>
    setSelected((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))

  const toggleAll = () => setSelected(allPicked ? [] : pickable.map((f) => f.id))

  const close = () => {
    if (!saving) onClose()
  }

  const confirm = async () => {
    if (selected.length === 0 || saving) return
    setSaving(true)
    setError(null)
    try {
      await onConfirm(selected)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setSaving(false)
    }
  }

  const count = selected.length

  if (files.length === 0) {
    return (
      <Modal open onClose={close} title="No documents yet" size="sm">
        <div className="sources-empty">
          <span className="sources-empty__icon">
            <FileIcon size={22} />
          </span>
          <p>Chats answer from documents in your library. Upload a PDF first, then start a chat about it.</p>
          <Button variant="primary" leftIcon={<UploadIcon size={15} />} onClick={onGoToDocuments}>
            Go to Documents
          </Button>
        </div>
      </Modal>
    )
  }

  return (
    <Modal
      open
      onClose={close}
      title="Choose documents"
      description="The chat answers only from these documents. To use different ones later, start a new chat."
      size="md"
      footer={
        <div className="sources-foot">
          <span className="sources-foot__count" aria-live="polite">
            {count === 0 ? 'Nothing selected' : `${count} selected`}
          </span>
          <Button variant="secondary" onClick={close} disabled={saving}>
            Cancel
          </Button>
          <Button variant="primary" onClick={() => void confirm()} loading={saving} disabled={count === 0}>
            Start chat
          </Button>
        </div>
      }
    >
      <div className="sources-dialog">
        {files.length > 6 && (
          <input
            type="search"
            className="sources-dialog__search"
            placeholder="Search documents"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search documents"
          />
        )}

        <div className="sources-dialog__bar">
          <span>{files.length} document{files.length === 1 ? '' : 's'}</span>
          {pickable.length > 1 && (
            <button type="button" className="sources-dialog__all" onClick={toggleAll}>
              {allPicked ? 'Clear all' : 'Select all'}
            </button>
          )}
        </div>

        <ul className="sources-list" role="listbox" aria-multiselectable="true" aria-label="Documents">
          {visible.map((file) => {
            const blocked = UNAVAILABLE[file.status]
            const checked = selected.includes(file.id)
            return (
              <li key={file.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={checked}
                  className={`sources-row ${checked ? 'is-checked' : ''}`}
                  onClick={() => toggle(file.id)}
                  disabled={Boolean(blocked) || saving}
                >
                  <span className="sources-row__check" aria-hidden>
                    <CheckIcon size={12} />
                  </span>
                  <span className="sources-row__main">
                    <span className="sources-row__name" title={file.filename}>
                      {file.filename.replace(/\.pdf$/i, '')}
                    </span>
                    <span className="sources-row__meta">
                      {blocked ?? (file.pagesParsed ? `${file.pagesParsed} page${file.pagesParsed === 1 ? '' : 's'}` : 'Ready')}
                      {file.uploadedBy ? ` · ${file.uploadedBy}` : ''}
                    </span>
                  </span>
                </button>
              </li>
            )
          })}
          {visible.length === 0 && <li className="sources-list__none">No documents match “{query}”.</li>}
        </ul>

        {error && (
          <div className="notice notice--danger" role="alert">
            {error}
          </div>
        )}
      </div>
    </Modal>
  )
}
