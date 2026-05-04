import { useState } from 'react'
import type { FileEntry, SafeUser } from '../../types'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { updateFileAccess } from '../../services/fileService'
import './AccessManagerDialog.css'

type Props = {
  open: boolean
  file: FileEntry | null
  employees: SafeUser[]
  onClose: () => void
}

export function AccessManagerDialog({ open, file, employees, onClose }: Props) {
  if (!file) return null
  return (
    <AccessManagerDialogInner
      key={file.id}
      open={open}
      file={file}
      employees={employees}
      onClose={onClose}
    />
  )
}

type InnerProps = {
  open: boolean
  file: FileEntry
  employees: SafeUser[]
  onClose: () => void
}

function AccessManagerDialogInner({ open, file, employees, onClose }: InnerProps) {
  const [accessIds, setAccessIds] = useState<string[]>(() => file.accessList)

  const toggle = (id: string) => {
    setAccessIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }

  const handleSave = () => {
    updateFileAccess(file.id, accessIds)
    onClose()
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Manage access"
      description={`Choose which employees can query "${file.filename}".`}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={handleSave}>Save changes</Button>
        </>
      }
    >
      <div className="access-dialog">
        {employees.length === 0 ? (
          <div className="access-dialog__empty">
            No employees yet. Create one from the Users tab to grant access.
          </div>
        ) : (
          <div className="access-dialog__list">
            {employees.map((emp) => {
              const checked = accessIds.includes(emp.id)
              return (
                <label
                  key={emp.id}
                  className={`access-dialog__row ${checked ? 'is-checked' : ''}`}
                >
                  <span className="access-dialog__name">{emp.username}</span>
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggle(emp.id)}
                  />
                </label>
              )
            })}
          </div>
        )}
      </div>
    </Modal>
  )
}
