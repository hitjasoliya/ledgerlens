import { useCallback, useMemo, useState, useEffect } from 'react'
import type { ReactNode } from 'react'
import type { Role, SafeUser } from '../types'
import { authenticate } from '../services/userService'
import { readJSON, removeKey, StorageKeys, writeJSON } from '../lib/storage'
import { getProfile } from '../lib/api'
import { AuthContext } from './authContextValue'

type StoredSession = { token: string; userId: string }

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SafeUser | null>(null)
  const [loading, setLoading] = useState(true)

  // Hydrate user profile from backend on mount if token exists
  useEffect(() => {
    const session = readJSON<StoredSession | null>(StorageKeys.session, null)
    if (session?.token) {
      getProfile()
        .then((profile) => {
          setUser(profile as SafeUser)
        })
        .catch((err) => {
          console.error('Failed to restore session:', err)
          removeKey(StorageKeys.session)
        })
        .finally(() => {
          setLoading(false)
        })
    } else {
      setLoading(false)
    }
  }, [])

  const login = useCallback(
    async (username: string, password: string, role: Role): Promise<SafeUser> => {
      const result = await authenticate(username, password, role)
      if (!result) throw new Error('Invalid credentials')
      
      const { access_token, user: matched } = result
      writeJSON<StoredSession>(StorageKeys.session, { 
        token: access_token, 
        userId: matched.id 
      })
      setUser(matched)
      return matched
    },
    [],
  )

  const logout = useCallback(() => {
    removeKey(StorageKeys.session)
    setUser(null)
  }, [])

  const refresh = useCallback(async () => {
    try {
      const profile = await getProfile()
      setUser(profile as SafeUser)
    } catch {
      setUser(null)
    }
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

  if (loading) {
    return (
      <div 
        style={{
          display: 'flex',
          height: '100vh',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'system-ui, sans-serif',
          color: '#374151'
        }}
      >
        Loading CapitalQuery...
      </div>
    )
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
