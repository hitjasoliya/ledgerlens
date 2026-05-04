import { createContext } from 'react'
import type { Role, SafeUser } from '../types'

export type AuthContextValue = {
  user: SafeUser | null
  isAuthenticated: boolean
  login: (username: string, password: string, role: Role) => SafeUser
  logout: () => void
  refresh: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)
