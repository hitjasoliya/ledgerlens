import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { Logo } from '../components/ui/Logo'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import type { Role } from '../types'
import { useAuth } from '../auth/useAuth'
import './Login.css'

export function Login() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { login, user } = useAuth()

  const initialRole: Role = params.get('role') === 'employee' ? 'employee' : 'admin'
  const [role, setRole] = useState<Role>(initialRole)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const helperText = useMemo(
    () =>
      role === 'admin'
        ? 'Admin — manage users, files, and access permissions.'
        : 'Employee — query permitted documents and attach files.',
    [role],
  )

  if (user) {
    return <Navigate to={user.role === 'admin' ? '/admin' : '/employee'} replace />
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const u = await login(username.trim(), password, role)
      navigate(u.role === 'admin' ? '/admin' : '/employee', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setSubmitting(false)
    }
  }

  const handleRoleChange = (next: Role) => {
    setRole(next)
    setError(null)
  }

  return (
    <div className="login">
      <div className="login__scanline" aria-hidden />

      <button
        type="button"
        className="login__back"
        onClick={() => navigate('/')}
      >
        &larr; Back
      </button>

      <div className="login__card">
        <div className="login__brand">
          <Logo size="md" />
        </div>

        <div className="login__role-toggle" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={role === 'admin'}
            className={`login__role-btn ${role === 'admin' ? 'is-active' : ''}`}
            onClick={() => handleRoleChange('admin')}
          >
            Admin
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={role === 'employee'}
            className={`login__role-btn ${role === 'employee' ? 'is-active' : ''}`}
            onClick={() => handleRoleChange('employee')}
          >
            Employee
          </button>
        </div>

        <header className="login__header">
          <h1 className="login__title">Authenticate</h1>
          <p className="login__subtitle">{helperText}</p>
        </header>

        <form className="login__form" onSubmit={handleSubmit}>
          <Input
            label="Username"
            name="username"
            value={username}
            onChange={(e) => {
              setUsername(e.target.value)
              if (error) setError(null)
            }}
            placeholder={role === 'admin' ? 'admin' : 'username'}
            autoComplete="username"
            required
          />
          <Input
            label="Password"
            name="password"
            type="password"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value)
              if (error) setError(null)
            }}
            placeholder="········"
            autoComplete="current-password"
            required
            error={error ?? undefined}
          />

          <Button
            type="submit"
            fullWidth
            size="lg"
            variant="primary"
            loading={submitting}
          >
            Continue as {role}
          </Button>
        </form>

        {role === 'admin' ? (
          <p className="login__hint">
            Default: <code>admin</code> / <code>admin123</code>
          </p>
        ) : (
          <p className="login__hint">
            Contact your administrator for credentials.
          </p>
        )}
      </div>
    </div>
  )
}
