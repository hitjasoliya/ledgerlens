import { useMemo } from 'react'
import { DashboardShell } from '../components/layout/DashboardShell'
import type { DashboardTab } from '../components/layout/DashboardShell'
import { ChatShell } from '../components/chat/ChatShell'
import { AdminFileManager } from '../components/files/AdminFileManager'
import { UserManager } from '../components/users/UserManager'
import { MessageIcon, FolderIcon, UsersIcon, SparklesIcon } from '../components/ui/Icon'
import { useAuth } from '../auth/useAuth'
import { useAdminFiles } from '../services/hooks'
import { LayoutInspector } from '../components/layout/LayoutInspector'

export function AdminDashboard() {
  const { user } = useAuth()
  const files = useAdminFiles()

  const tabs = useMemo<DashboardTab[]>(() => {
    if (!user) return []
    return [
      {
        id: 'chat',
        label: 'Chat',
        icon: <MessageIcon size={16} />,
        content: (
          <ChatShell
            user={user}
            accessibleFiles={files}
            allowFileAttach
            fileScope="admin"
          />
        ),
      },
      {
        id: 'files',
        label: 'Files',
        icon: <FolderIcon size={16} />,
        content: <AdminFileManager uploader={user} />,
      },
      {
        id: 'users',
        label: 'Users',
        icon: <UsersIcon size={16} />,
        content: <UserManager currentUserId={user.id} />,
      },
      {
        id: 'inspector',
        label: 'Layout Inspector',
        icon: <SparklesIcon size={16} />,
        content: <LayoutInspector />,
      },
    ]
  }, [user, files])

  if (!user) return null

  return <DashboardShell user={user} tabs={tabs} defaultTab="chat" />
}
