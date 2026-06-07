import { createContext } from 'react'
import type { Role, SafeUser } from '../types'

export type AuthContextValue = {
  user: SafeUser | null
  isAuthenticated: boolean
  login: (username: string, password: string, role: Role) => Promise<SafeUser>
  logout: () => void
  refresh: () => Promise<void>
}

export const AuthContext = createContext<AuthContextValue | null>(null)
