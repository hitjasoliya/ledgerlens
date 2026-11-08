import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { Logo } from '../components/ui/Logo'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { useAuth } from '../auth/useAuth'
import './Login.css'

export function Login() {
  const navigate = useNavigate()
  const { login, user } = useAuth()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)


  if (user) {
    return <Navigate to={user.role === 'admin' ? '/admin' : '/employee'} replace />
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const u = await login(username.trim(), password)
      navigate(u.role === 'admin' ? '/admin' : '/employee', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setSubmitting(false)
    }
  }


  return (
    <div className="login">
      <button type="button" className="login__back" onClick={() => navigate('/')}>
        <Logo size="sm" />
      </button>

      <div className="login__panel">
        <header className="login__header">
          <h1 className="login__title">Welcome back</h1>
          <p className="login__subtitle">Sign in with the account your administrator gave you.</p>
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
            autoComplete="username"
            autoFocus
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
            autoComplete="current-password"
            required
            error={error ?? undefined}
          />

          <Button type="submit" fullWidth size="lg" variant="primary" loading={submitting}>
            Continue
          </Button>
        </form>
      </div>
    </div>
  )
}
