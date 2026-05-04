import { useMemo } from 'react'
import type { FileEntry } from '../types'
import { DashboardShell } from '../components/layout/DashboardShell'
import type { DashboardTab } from '../components/layout/DashboardShell'
import { ChatShell } from '../components/chat/ChatShell'
import { EmployeeFileLibrary } from '../components/files/EmployeeFileLibrary'
import { MessageIcon, FolderIcon } from '../components/ui/Icon'
import { useAuth } from '../auth/useAuth'
import { useAccessibleFiles, useOwnFiles } from '../services/hooks'

export function EmployeeDashboard() {
  const { user } = useAuth()
  const shared = useAccessibleFiles(user?.id ?? '')
  const own = useOwnFiles(user?.id ?? '')

  const accessible = useMemo<FileEntry[]>(() => {
    const seen = new Set<string>()
    const merged: FileEntry[] = []
    for (const f of [...shared, ...own]) {
      if (seen.has(f.id)) continue
      seen.add(f.id)
      merged.push(f)
    }
    return merged
  }, [shared, own])

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
            accessibleFiles={accessible}
            allowFileAttach
            fileScope="employee"
          />
        ),
      },
      {
        id: 'files',
        label: 'Files',
        icon: <FolderIcon size={16} />,
        content: <EmployeeFileLibrary user={user} />,
      },
    ]
  }, [user, accessible])

  if (!user) return null

  return <DashboardShell user={user} tabs={tabs} defaultTab="chat" />
}
