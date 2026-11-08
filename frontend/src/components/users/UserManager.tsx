import { useState } from 'react'
import type { SafeUser } from '../../types'
import { Avatar } from '../ui/Avatar'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { PlusIcon, TrashIcon } from '../ui/Icon'
import { CreateUserDialog } from './CreateUserDialog'
import { deleteUser } from '../../services/userService'
import { useUsers } from '../../services/hooks'
import { formatDate } from '../../lib/format'
import './UserManager.css'

type Props = {
  currentUserId: string
}

export function UserManager({ currentUserId }: Props) {
  const users = useUsers()
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<SafeUser | null>(null)
  const [transferAdminId, setTransferAdminId] = useState<string>('')
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  const candidateAdmins = users.filter(
    (u) => u.role === 'admin' && (!deleteTarget || u.id !== deleteTarget.id),
  )

  const openDeleteDialog = (user: SafeUser) => {
    if (user.id === currentUserId) return
    setDeleteTarget(user)
    setDeleteError(null)
    const firstAdmin = users.find(
      (u) => u.role === 'admin' && u.id !== user.id,
    )
    setTransferAdminId(firstAdmin?.id ?? '')
  }

  const closeDeleteDialog = () => {
    if (deleting) return
    setDeleteTarget(null)
    setDeleteError(null)
  }

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    setDeleteError(null)

    try {
      await deleteUser(deleteTarget.id, transferAdminId || undefined)
      setDeleteTarget(null)
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : String(err))
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="page">
      <div className="page__inner">
        <header className="page__header">
          <div>
            <h1 className="page__title">Users</h1>
            <p className="page__subtitle">
              Create accounts for admins and employees. Only admins can manage users.
            </p>
          </div>
          <Button variant="primary" leftIcon={<PlusIcon size={15} />} onClick={() => setCreateOpen(true)}>
            Add user
          </Button>
        </header>

        <ul className="users">
          {users.map((user) => {
            const isSelf = user.id === currentUserId
            return (
              <li key={user.id} className="users__row">
                <Avatar name={user.username} variant={user.role === 'admin' ? 'accent' : 'neutral'} />
                <div className="users__main">
                  <span className="users__name">
                    {user.username}
                    {isSelf && <span className="users__you">You</span>}
                  </span>
                  <span className="users__meta">Added {formatDate(user.createdAt)}</span>
                </div>
                <span className="users__role">{user.role === 'admin' ? 'Admin' : 'Employee'}</span>
                <div className="users__actions">
                  {!isSelf && (
                    <button
                      type="button"
                      className="icon-btn icon-btn--danger"
                      aria-label={`Delete user ${user.username}`}
                      title="Delete user"
                      onClick={() => openDeleteDialog(user)}
                    >
                      <TrashIcon size={16} />
                    </button>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      </div>

      <CreateUserDialog open={createOpen} onClose={() => setCreateOpen(false)} />

      {deleteTarget && (
        <Modal
          open={Boolean(deleteTarget)}
          onClose={closeDeleteDialog}
          title={`Delete ${deleteTarget.username}?`}
          description="Removes the account and transfers its documents to another admin."
          size="sm"
          footer={
            <>
              <Button variant="secondary" onClick={closeDeleteDialog} disabled={deleting}>
                Cancel
              </Button>
              <Button
                variant="danger"
                onClick={handleConfirmDelete}
                loading={deleting}
                disabled={deleting || (candidateAdmins.length === 0 && deleteTarget.role === 'admin')}
              >
                Delete account
              </Button>
            </>
          }
        >
          <div className="delete-user">
            {deleteError && (
              <div className="notice notice--danger" role="alert">
                {deleteError}
              </div>
            )}

            <p className="delete-user__text">
              Their private conversations are deleted and their sessions are signed out. This can’t be undone.
            </p>

            {candidateAdmins.length === 0 ? (
              <div className="notice notice--warning">
                No other administrator exists to receive document ownership.
              </div>
            ) : (
              <label className="delete-user__field">
                <span>Transfer documents to</span>
                <select
                  className="delete-user__select"
                  value={transferAdminId}
                  disabled={deleting}
                  onChange={(e) => setTransferAdminId(e.target.value)}
                >
                  {candidateAdmins.map((admin) => (
                    <option key={admin.id} value={admin.id}>
                      {admin.username}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
        </Modal>
      )}
    </div>
  )
}
