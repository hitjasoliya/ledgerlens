import { Navigate, useLocation } from 'react-router-dom'
import type { ReactNode } from 'react'
import type { Role } from '../types'
import { useAuth } from './useAuth'

type Props = {
  role: Role
  children: ReactNode
}

export function ProtectedRoute({ role, children }: Props) {
  const { user } = useAuth()
  const location = useLocation()

  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname, role }} replace />
  }

  if (user.role !== role) {
    const target = user.role === 'admin' ? '/admin' : '/employee'
    return <Navigate to={target} replace />
  }

  return <>{children}</>
}
