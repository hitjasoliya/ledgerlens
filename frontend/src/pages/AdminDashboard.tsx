import { useMemo } from 'react'
import { AppShell } from '../components/layout/AppShell'
import type { ShellPage } from '../components/layout/AppShell'
import { AdminFileManager } from '../components/files/AdminFileManager'
import { UserManager } from '../components/users/UserManager'
import { FolderIcon, UsersIcon } from '../components/ui/Icon'
import { useAuth } from '../auth/useAuth'
import { useAdminFilesState } from '../services/hooks'

export function AdminDashboard() {
  const { user } = useAuth()
  const { files, loading: filesLoading } = useAdminFilesState()

  const pages = useMemo<ShellPage[]>(() => {
    if (!user) return []
    return [
      {
        id: 'files',
        label: 'Documents',
        icon: <FolderIcon size={16} />,
        content: <AdminFileManager uploader={user} />,
      },
      {
        id: 'users',
        label: 'Users',
        icon: <UsersIcon size={16} />,
        content: <UserManager currentUserId={user.id} />,
      },
    ]
  }, [user])

  if (!user) return null

  return <AppShell key={user.id} user={user} accessibleFiles={files} filesLoading={filesLoading} pages={pages} />
}
