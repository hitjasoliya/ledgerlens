import { useMemo } from 'react'
import type { FileEntry } from '../types'
import { AppShell } from '../components/layout/AppShell'
import type { ShellPage } from '../components/layout/AppShell'
import { EmployeeFileLibrary } from '../components/files/EmployeeFileLibrary'
import { FolderIcon } from '../components/ui/Icon'
import { useAuth } from '../auth/useAuth'
import { useAccessibleFilesState, useOwnFilesState } from '../services/hooks'

export function EmployeeDashboard() {
  const { user } = useAuth()
  const { files: shared, loading: sharedLoading } = useAccessibleFilesState(user?.id ?? '')
  const { files: own, loading: ownLoading } = useOwnFilesState(user?.id ?? '')

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

  const pages = useMemo<ShellPage[]>(() => {
    if (!user) return []
    return [
      {
        id: 'files',
        label: 'Documents',
        icon: <FolderIcon size={16} />,
        content: <EmployeeFileLibrary user={user} />,
      },
    ]
  }, [user])

  if (!user) return null

  return <AppShell key={user.id} user={user} accessibleFiles={accessible} filesLoading={sharedLoading || ownLoading} pages={pages} />
}
