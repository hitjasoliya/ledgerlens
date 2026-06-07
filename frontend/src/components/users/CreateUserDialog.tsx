import { useState } from 'react'
import type { FormEvent } from 'react'
import type { Role } from '../../types'
import { Modal } from '../ui/Modal'
import { Input } from '../ui/Input'
import { Button } from '../ui/Button'
import { createUser } from '../../services/userService'
import './CreateUserDialog.css'

type Props = {
  open: boolean
  onClose: () => void
  createdBy: string
}

export function CreateUserDialog({ open, onClose, createdBy }: Props) {
  if (!open) return null
  return (
    <CreateUserDialogInner
      key={String(open)}
      open={open}
      onClose={onClose}
      createdBy={createdBy}
    />
  )
}

function CreateUserDialogInner({ open, onClose, createdBy }: Props) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<Role>('employee')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await createUser({
        username: username.trim(),
        password,
        role,
        createdBy,
      })
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
      onClose={onClose}
      title="Create user"
      description="Add a new admin or employee account."
      size="sm"
    >
      <form className="create-user" onSubmit={handleSubmit}>
        <div className="create-user__role">
          <label
            className={`create-user__role-opt ${role === 'employee' ? 'is-active' : ''}`}
          >
            <input
              type="radio"
              name="role"
              value="employee"
              checked={role === 'employee'}
              onChange={() => setRole('employee')}
            />
            <span className="create-user__role-title">Employee</span>
            <span className="create-user__role-desc">Query permitted documents</span>
          </label>
          <label
            className={`create-user__role-opt ${role === 'admin' ? 'is-active' : ''}`}
          >
            <input
              type="radio"
              name="role"
              value="admin"
              checked={role === 'admin'}
              onChange={() => setRole('admin')}
            />
            <span className="create-user__role-title">Admin</span>
            <span className="create-user__role-desc">Manage users, files, access</span>
          </label>
        </div>

        <Input
          label="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="e.g. priya.kumar"
          required
        />
        <Input
          label="Password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Minimum 4 characters"
          required
          minLength={4}
          error={error ?? undefined}
        />

        <div className="create-user__actions">
          <Button variant="secondary" onClick={onClose} type="button">
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={submitting}>
            Create user
          </Button>
        </div>
      </form>
    </Modal>
  )
}
