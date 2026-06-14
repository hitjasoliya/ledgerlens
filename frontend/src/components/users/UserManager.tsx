import { useState } from 'react'
import type { SafeUser } from '../../types'
import { Avatar } from '../ui/Avatar'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
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
  const [open, setOpen] = useState(false)

  const handleDelete = async (user: SafeUser) => {
    if (user.id === currentUserId) return
    if (!confirm(`Remove user "${user.username}"?`)) return
    try {
      await deleteUser(user.id)
    } catch (e) {
      alert(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div className="user-manager">
      <header className="user-manager__header">
        <div>
          <h2 className="user-manager__title">Users & access</h2>
          <p className="user-manager__subtitle">
            Create credentials for admins and employees. Only admins can manage users.
          </p>
        </div>
        <Button
          variant="primary"
          leftIcon={<PlusIcon size={14} />}
          onClick={() => setOpen(true)}
        >
          Create user
        </Button>
      </header>

      <div className="user-manager__list">
        <div className="user-manager__list-head">
          <span>Member</span>
          <span>Role</span>
          <span>Created</span>
          <span></span>
        </div>
        {users.map((user) => {
          const isSelf = user.id === currentUserId
          return (
            <div key={user.id} className="user-manager__row">
              <div className="user-manager__member">
                <Avatar
                  name={user.username}
                  variant={user.role === 'admin' ? 'neutral' : 'accent'}
                />
                <div>
                  <div className="user-manager__name">
                    {user.username}
                    {isSelf && <span className="user-manager__you">you</span>}
                  </div>
                </div>
              </div>
              <div>
                <Badge tone={user.role === 'admin' ? 'accent' : 'neutral'}>
                  {user.role}
                </Badge>
              </div>
              <div className="user-manager__date">{formatDate(user.createdAt)}</div>
              <div className="user-manager__actions">
                {!isSelf && (
                  <button
                    type="button"
                    className="user-manager__delete"
                    aria-label="Delete user"
                    onClick={() => handleDelete(user)}
                  >
                    <TrashIcon size={14} />
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      <CreateUserDialog
        open={open}
        onClose={() => setOpen(false)}
        createdBy={currentUserId}
      />
    </div>
  )
}
