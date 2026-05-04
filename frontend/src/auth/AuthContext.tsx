import { useCallback, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { Role, SafeUser } from '../types'
import {
  authenticate,
  ensureSeed,
  findById,
} from '../services/userService'
import { readJSON, removeKey, StorageKeys, writeJSON } from '../lib/storage'
import { AuthContext } from './authContextValue'

type StoredSession = { userId: string }

function hydrateUser(): SafeUser | null {
  ensureSeed()
  const stored = readJSON<StoredSession | null>(StorageKeys.session, null)
  if (!stored?.userId) return null
  return findById(stored.userId)
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SafeUser | null>(hydrateUser)

  const login = useCallback(
    (username: string, password: string, role: Role): SafeUser => {
      const matched = authenticate(username, password, role)
      if (!matched) throw new Error('Invalid credentials')
      writeJSON<StoredSession>(StorageKeys.session, { userId: matched.id })
      setUser(matched)
      return matched
    },
    [],
  )

  const logout = useCallback(() => {
    removeKey(StorageKeys.session)
    setUser(null)
  }, [])

  const refresh = useCallback(() => {
    setUser(hydrateUser())
  }, [])

  const value = useMemo(
    () => ({
      user,
      isAuthenticated: !!user,
      login,
      logout,
      refresh,
    }),
    [user, login, logout, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
