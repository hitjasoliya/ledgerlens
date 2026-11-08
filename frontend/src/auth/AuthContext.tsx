import { useCallback, useMemo, useState, useEffect } from 'react'
import type { ReactNode } from 'react'
import type { SafeUser } from '../types'
import { authenticate } from '../services/userService'
import { readJSON, removeKey, StorageKeys, writeJSON } from '../lib/storage'
import { getProfile, logoutUser, ApiError } from '../lib/api'
import { AuthContext } from './authContextValue'
import { Logo } from '../components/ui/Logo'
import { Button } from '../components/ui/Button'
import '../pages/Login.css'

type StoredSession = { token: string; userId: string }

function readStoredToken(): string | undefined {
  return readJSON<StoredSession | null>(StorageKeys.session, null)?.token
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SafeUser | null>(null)
  const [initialToken] = useState(readStoredToken)
  const [loading, setLoading] = useState(Boolean(initialToken))
  const [restoreError, setRestoreError] = useState<string | null>(null)
  const [retrying, setRetrying] = useState(false)

  const restoreSession = useCallback(async (token: string) => {
    try {
      const profile = await getProfile()
      if (readStoredToken() !== token) return
      setUser(profile)
      setRestoreError(null)
    } catch (err) {
      if (readStoredToken() !== token) return
      if (err instanceof ApiError && err.status === 401) {
        removeKey(StorageKeys.session)
        setUser(null)
        setRestoreError(null)
      } else {
        setRestoreError(err instanceof Error ? err.message : 'Authentication service is unavailable')
      }
    } finally {
      setLoading(false)
      setRetrying(false)
    }
  }, [])

  useEffect(() => {
    if (!initialToken) return
    const controller = new AbortController()

    getProfile()
      .then((profile) => {
        if (!controller.signal.aborted && readStoredToken() === initialToken) {
          setUser(profile)
          setRestoreError(null)
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted && readStoredToken() === initialToken) {
          if (err instanceof ApiError && err.status === 401) {
            removeKey(StorageKeys.session)
            setUser(null)
            setRestoreError(null)
          } else {
            setRestoreError(
              err instanceof Error
                ? err.message
                : 'Authentication service is unavailable',
            )
          }
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false)
          setRetrying(false)
        }
      })

    return () => {
      controller.abort()
    }
  }, [initialToken])

  useEffect(() => {
    const handleUnauthorized = () => {
      removeKey(StorageKeys.session)
      setUser(null)
      setRestoreError(null)
    }
    window.addEventListener('ledgerlens:unauthorized', handleUnauthorized)
    return () => window.removeEventListener('ledgerlens:unauthorized', handleUnauthorized)
  }, [])

  const login = useCallback(
    async (username: string, password: string): Promise<SafeUser> => {
      const result = await authenticate(username, password)
      const { access_token, user: matched } = result
      writeJSON<StoredSession>(StorageKeys.session, { 
        token: access_token, 
        userId: matched.id 
      })
      setUser(matched)
      setRestoreError(null)
      return matched
    },
    [],
  )

  const logout = useCallback(async (): Promise<void> => {
    const token = readStoredToken()
    try {
      await logoutUser()
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 401)) throw err
    }
    const current = readStoredToken()
    if (current && current !== token) {
      throw new Error('Your active session changed. Retry logout.')
    }
    removeKey(StorageKeys.session)
    setUser(null)
    setRestoreError(null)
  }, [])

  const refresh = useCallback(async (): Promise<void> => {
    const token = readStoredToken()
    if (!token) {
      setUser(null)
      return
    }
    try {
      const profile = await getProfile()
      if (readStoredToken() === token) setUser(profile)
    } catch (err) {
      if (readStoredToken() !== token) return
      if (err instanceof ApiError && err.status === 401) {
        removeKey(StorageKeys.session)
        setUser(null)
        return
      }
      throw err
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
      <div className="auth-screen" role="status">
        <Logo size="md" showWordmark={false} />
      </div>
    )
  }

  if (restoreError && !user) {
    return (
      <div className="login" role="region" aria-label="Sign-in service unavailable">
        <div className="login__panel">
          <Logo size="lg" showWordmark={false} />
          <header className="login__header">
            <h1 className="login__title">Can’t reach sign-in</h1>
            <p className="login__subtitle">
              The authentication service is unavailable, so your session couldn’t be checked. You’re still signed in on this device.
            </p>
          </header>

          <div className="notice notice--danger" role="alert">
            {restoreError}
          </div>

          <Button
            variant="primary"
            size="lg"
            onClick={() => {
              const token = readStoredToken()
              if (!token) {
                setRestoreError(null)
                return
              }
              setRetrying(true)
              void restoreSession(token)
            }}
            loading={retrying}
            disabled={retrying}
            fullWidth
          >
            Try again
          </Button>
        </div>
      </div>
    )
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
