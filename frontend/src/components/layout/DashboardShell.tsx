import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import type { SafeUser } from '../../types'
import { Logo } from '../ui/Logo'
import { Avatar } from '../ui/Avatar'
import { Badge } from '../ui/Badge'
import { LogoutIcon, MenuIcon, CloseIcon, SunIcon, MoonIcon } from '../ui/Icon'
import { useAuth } from '../../auth/useAuth'
import './DashboardShell.css'

export type DashboardTab = {
  id: string
  label: string
  icon: ReactNode
  content: ReactNode
}

type Props = {
  user: SafeUser
  tabs: DashboardTab[]
  defaultTab?: string
}

export function DashboardShell({ user, tabs, defaultTab }: Props) {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [activeId, setActiveId] = useState(defaultTab ?? tabs[0]?.id)
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      const saved = localStorage.getItem('sidebar_collapsed')
      return saved === 'true'
    } catch {
      return false
    }
  })
  
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    try {
      const saved = localStorage.getItem('theme') as 'light' | 'dark'
      if (saved) {
        document.documentElement.setAttribute('data-theme', saved)
        return saved
      }
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
      const defaultTheme = prefersDark ? 'dark' : 'light'
      document.documentElement.setAttribute('data-theme', defaultTheme)
      return defaultTheme
    } catch {
      return 'light'
    }
  })

  const toggleTheme = () => {
    setTheme(prev => {
      const next = prev === 'light' ? 'dark' : 'light'
      document.documentElement.setAttribute('data-theme', next)
      try {
        localStorage.setItem('theme', next)
      } catch {}
      return next
    })
  }

  const toggleSidebar = () => {
    setSidebarCollapsed((prev) => {
      const next = !prev
      try {
        localStorage.setItem('sidebar_collapsed', String(next))
      } catch (e) {
        console.error(e)
      }
      return next
    })
  }

  const active = useMemo(() => {
    const match = tabs.find((t) => t.id === activeId)
    return match ?? tabs[0] ?? null
  }, [tabs, activeId])

  const handleLogout = () => {
    logout()
    navigate('/', { replace: true })
  }

  return (
    <div className="dash">
      <aside className={`dash__nav ${sidebarCollapsed ? 'is-collapsed' : ''} ${mobileNavOpen ? 'is-open' : ''} dark-scroll`}>
        <div className="dash__nav-top">
          <Logo size="sm" variant="dark" />
          <button
            type="button"
            className="dash__nav-mobile-close"
            onClick={() => setMobileNavOpen(false)}
            aria-label="Close menu"
          >
            <CloseIcon size={16} />
          </button>
        </div>

        <nav className="dash__tabs">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`dash__tab ${tab.id === activeId ? 'is-active' : ''}`}
              onClick={() => {
                setActiveId(tab.id)
                setMobileNavOpen(false)
              }}
            >
              <span className="dash__tab-icon">{tab.icon}</span>
              <span className="dash__tab-label">{tab.label}</span>
            </button>
          ))}
        </nav>

        <div className="dash__nav-footer">
          <div className="dash__user">
            <Avatar
              name={user.username}
              size="sm"
              variant={user.role === 'admin' ? 'coral' : 'soft'}
            />
            <div className="dash__user-info">
              <span className="dash__user-name">{user.username}</span>
              <Badge tone={user.role === 'admin' ? 'coral' : 'neutral'}>
                {user.role}
              </Badge>
            </div>
          </div>
          <button
            type="button"
            className="dash__logout"
            onClick={handleLogout}
            aria-label="Logout"
            title="Logout"
          >
            <LogoutIcon size={16} />
          </button>
        </div>
      </aside>

      <div className="dash__main">
        <header className="dash__topbar">
          <button
            type="button"
            className="dash__menu-btn"
            onClick={() => {
              if (window.innerWidth <= 760) {
                setMobileNavOpen(true)
              } else {
                toggleSidebar()
              }
            }}
            aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            <MenuIcon size={18} />
          </button>
          <div className="dash__breadcrumb">
            <span className="dash__breadcrumb-app">CapitalQuery</span>
            <span className="dash__breadcrumb-sep">/</span>
            <span className="dash__breadcrumb-tab">{active?.label}</span>
          </div>
          <button
            type="button"
            className="dash__theme-btn"
            onClick={toggleTheme}
            aria-label="Toggle theme"
            title="Toggle theme"
            style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', justifyContent: 'center', width: '32px', height: '32px', borderRadius: '50%', color: 'var(--color-text-muted)' }}
          >
            {theme === 'light' ? <MoonIcon size={18} /> : <SunIcon size={18} />}
          </button>
        </header>

        <div className="dash__content">{active?.content}</div>
      </div>

      {mobileNavOpen && (
        <div
          className="dash__overlay"
          onClick={() => setMobileNavOpen(false)}
          role="presentation"
        />
      )}
    </div>
  )
}
