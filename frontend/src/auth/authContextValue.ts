import { createContext } from 'react'
import type { SafeUser } from '../types'

export type AuthContextValue = {
  user: SafeUser | null
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<SafeUser>
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)
