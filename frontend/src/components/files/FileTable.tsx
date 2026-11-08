import type { FileEntry, SafeUser } from '../../types'
import { FileIcon, RefreshIcon, TrashIcon, UsersIcon } from '../ui/Icon'
import { formatDate } from '../../lib/format'
import './FileTable.css'

type Column = 'access' | 'owner' | 'pages' | 'date'

type Props = {
  files: FileEntry[]
  employees?: SafeUser[]
  columns?: Column[]
  onManageAccess?: (file: FileEntry) => void
  onDelete?: (file: FileEntry) => void
  onRetry?: (file: FileEntry) => void
  deletingId?: string | null
  emptyTitle?: string
  emptyDescription?: string
}

const STATUS: Record<FileEntry['status'], { label: string; tone: string }> = {
  queued: { label: 'Queued', tone: 'pending' },
  processing: { label: 'Indexing', tone: 'pending' },
  searchable: { label: 'Ready', tone: 'ready' },
  failed: { label: 'Failed', tone: 'failed' },
  deleting: { label: 'Deleting', tone: 'muted' },
  cleanup_pending: { label: 'Removing', tone: 'muted' },
}

export function FileTable({
  files,
  employees = [],
  columns = ['access', 'owner', 'pages', 'date'],
  onManageAccess,
  onDelete,
  onRetry,
  deletingId = null,
  emptyTitle = 'No documents yet',
  emptyDescription = 'Uploaded documents will appear here.',
}: Props) {
  if (files.length === 0) {
    return (
      <div className="files-empty">
        <FileIcon size={20} />
        <p className="files-empty__title">{emptyTitle}</p>
        <p className="files-empty__desc">{emptyDescription}</p>
      </div>
    )
  }

  const employeeMap = new Map(employees.map((e) => [e.id, e.username]))
  const hasActions = Boolean(onManageAccess || onDelete || onRetry)

  return (
    <ul className="files">
      {files.map((file) => {
        const status = STATUS[file.status] ?? { label: file.status, tone: 'muted' }
        const meta: string[] = []
        if (columns.includes('owner')) meta.push(file.uploadedBy)
        if (columns.includes('pages') && file.pagesParsed) {
          meta.push(`${file.pagesParsed} page${file.pagesParsed === 1 ? '' : 's'}`)
        }
        if (columns.includes('date')) meta.push(formatDate(file.uploadedAt))

        return (
          <li key={file.id} className="files__row">
            <span className="files__icon" aria-hidden>
              <FileIcon size={16} />
            </span>

            <div className="files__main">
              <span className="files__name" title={file.filename}>
                {file.filename}
              </span>
              <span className="files__meta">
                <span className={`files__status files__status--${status.tone}`}>{status.label}</span>
                {meta.map((m, i) => (
                  <span key={i}>{m}</span>
                ))}
              </span>
              {file.status === 'failed' && file.errorMessage && (
                <span className="files__error" title={file.errorMessage}>
                  {file.errorMessage}
                </span>
              )}
            </div>

            {columns.includes('access') && (
              <div className="files__access" title="Employees who can ask about this document">
                {file.accessList.length === 0
                  ? 'Admins only'
                  : file.accessList
                      .slice(0, 2)
                      .map((id) => employeeMap.get(id) ?? id.slice(0, 6))
                      .join(', ') + (file.accessList.length > 2 ? ` +${file.accessList.length - 2}` : '')}
              </div>
            )}

            {hasActions && (
              <div className="files__actions">
                {onRetry && file.status === 'failed' && (
                  <button
                    type="button"
                    className="icon-btn"
                    onClick={() => onRetry(file)}
                    aria-label={`Retry ${file.filename}`}
                    title="Retry indexing"
                  >
                    <RefreshIcon size={16} />
                  </button>
                )}
                {onManageAccess && (
                  <button
                    type="button"
                    className="icon-btn"
                    onClick={() => onManageAccess(file)}
                    aria-label={`Manage access for ${file.filename}`}
                    title="Manage access"
                  >
                    <UsersIcon size={16} />
                  </button>
                )}
                {onDelete && (
                  <button
                    type="button"
                    className="icon-btn icon-btn--danger"
                    aria-label={deletingId === file.id ? 'Deleting file' : `Delete ${file.filename}`}
                    title="Delete"
                    disabled={deletingId !== null}
                    aria-busy={deletingId === file.id}
                    onClick={() => onDelete(file)}
                  >
                    <TrashIcon size={16} />
                  </button>
                )}
              </div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
