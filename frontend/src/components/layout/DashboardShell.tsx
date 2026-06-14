import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import type { SafeUser } from '../../types'
import { Logo } from '../ui/Logo'
import { Avatar } from '../ui/Avatar'
import { Badge } from '../ui/Badge'
import { LogoutIcon, MenuIcon, CloseIcon } from '../ui/Icon'
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
      return localStorage.getItem('sidebar_collapsed') === 'true'
    } catch {
      return false
    }
  })

  const toggleSidebar = () => {
    setSidebarCollapsed((prev) => {
      const next = !prev
      try { localStorage.setItem('sidebar_collapsed', String(next)) } catch {}
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
      <aside className={`dash__nav ${sidebarCollapsed ? 'is-collapsed' : ''} ${mobileNavOpen ? 'is-open' : ''}`}>
        <div className="dash__nav-top">
          <Logo size="sm" variant="dark" />
          <button
            type="button"
            className="dash__nav-mobile-close"
            onClick={() => setMobileNavOpen(false)}
            aria-label="Close menu"
          >
            <CloseIcon size={14} />
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
              variant={user.role === 'admin' ? 'accent' : 'neutral'}
            />
            <div className="dash__user-info">
              <span className="dash__user-name">{user.username}</span>
              <Badge tone={user.role === 'admin' ? 'accent' : 'neutral'} size="sm">
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
            <LogoutIcon size={14} />
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
            aria-label={sidebarCollapsed ? "Show sidebar" : "Hide sidebar"}
          >
            <MenuIcon size={16} />
          </button>
          <div className="dash__breadcrumb">
            <span className="dash__breadcrumb-app">LedgerLens</span>
            <span className="dash__breadcrumb-sep">/</span>
            <span className="dash__breadcrumb-tab">{active?.label}</span>
          </div>
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
