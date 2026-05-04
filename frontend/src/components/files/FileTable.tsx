import type { FileEntry, SafeUser } from '../../types'
import { FileIcon, TrashIcon, UsersIcon } from '../ui/Icon'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { formatDate } from '../../lib/format'
import './FileTable.css'

type Column = 'access' | 'owner' | 'pages' | 'date'

type Props = {
  files: FileEntry[]
  employees?: SafeUser[]
  columns?: Column[]
  onManageAccess?: (file: FileEntry) => void
  onDelete?: (file: FileEntry) => void
  emptyTitle?: string
  emptyDescription?: string
}

export function FileTable({
  files,
  employees = [],
  columns = ['access', 'owner', 'pages', 'date'],
  onManageAccess,
  onDelete,
  emptyTitle = 'No documents yet',
  emptyDescription = 'Uploaded documents will appear here.',
}: Props) {
  if (files.length === 0) {
    return (
      <div className="file-table__empty">
        <div className="file-table__empty-icon">
          <FileIcon size={20} />
        </div>
        <h4>{emptyTitle}</h4>
        <p>{emptyDescription}</p>
      </div>
    )
  }

  const employeeMap = new Map(employees.map((e) => [e.id, e.username]))

  return (
    <div className="file-table">
      <div className="file-table__head">
        <span>Document</span>
        {columns.includes('access') && <span>Access</span>}
        {columns.includes('owner') && <span>Owner</span>}
        {columns.includes('pages') && <span>Pages</span>}
        {columns.includes('date') && <span>Uploaded</span>}
        {(onManageAccess || onDelete) && <span></span>}
      </div>

      {files.map((file) => (
        <div key={file.id} className="file-table__row">
          <div className="file-table__name">
            <div className="file-table__name-icon">
              <FileIcon size={14} />
            </div>
            <div className="file-table__name-text">
              <span className="file-table__filename">{file.filename}</span>
              <span className="file-table__chunks">
                {file.chunksIndexed} chunks · {file.scope === 'admin' ? 'shared' : 'personal'}
              </span>
            </div>
          </div>

          {columns.includes('access') && (
            <div className="file-table__access">
              {file.scope === 'admin' ? (
                file.accessList.length === 0 ? (
                  <Badge tone="neutral">Admins only</Badge>
                ) : (
                  <div className="file-table__access-list">
                    {file.accessList.slice(0, 2).map((id) => (
                      <Badge key={id} tone="coral">
                        {employeeMap.get(id) ?? id.slice(0, 6)}
                      </Badge>
                    ))}
                    {file.accessList.length > 2 && (
                      <Badge tone="neutral">+{file.accessList.length - 2}</Badge>
                    )}
                  </div>
                )
              ) : (
                <Badge tone="neutral">Personal</Badge>
              )}
            </div>
          )}

          {columns.includes('owner') && (
            <div className="file-table__owner">{file.uploadedBy}</div>
          )}

          {columns.includes('pages') && (
            <div className="file-table__pages">{file.pagesParsed}</div>
          )}

          {columns.includes('date') && (
            <div className="file-table__date">{formatDate(file.uploadedAt)}</div>
          )}

          {(onManageAccess || onDelete) && (
            <div className="file-table__actions">
              {onManageAccess && file.scope === 'admin' && (
                <Button
                  size="sm"
                  variant="ghost"
                  leftIcon={<UsersIcon size={14} />}
                  onClick={() => onManageAccess(file)}
                >
                  Access
                </Button>
              )}
              {onDelete && (
                <button
                  type="button"
                  className="file-table__delete"
                  aria-label="Delete file"
                  onClick={() => onDelete(file)}
                >
                  <TrashIcon size={14} />
                </button>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
