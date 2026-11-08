import { useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import type { FileEntry, SafeUser } from '../../types'
import { Logo } from '../ui/Logo'
import { Avatar } from '../ui/Avatar'
import { EditIcon, LogoutIcon, SidebarIcon, TrashIcon } from '../ui/Icon'
import { ChatWindow } from '../chat/ChatWindow'
import { SourcesDialog } from '../chat/SourcesDialog'
import { useChat } from '../chat/useChat'
import { useAuth } from '../../auth/useAuth'
import './AppShell.css'

export type ShellPage = {
  id: string
  label: string
  icon: ReactNode
  content: ReactNode
}

type Props = {
  user: SafeUser
  accessibleFiles: FileEntry[]
  filesLoading?: boolean
  pages: ShellPage[]
}

const MOBILE_QUERY = '(max-width: 768px)'
const COLLAPSED_KEY = 'sidebar_collapsed'

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === 'true'
  } catch {
    return false
  }
}

export function AppShell({ user, accessibleFiles, filesLoading = false, pages }: Props) {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const chat = useChat({ ownerId: user.id })

  const [view, setView] = useState<string>('chat')
  const [collapsed, setCollapsed] = useState(readCollapsed)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [loggingOut, setLoggingOut] = useState(false)
  const [logoutError, setLogoutError] = useState<string | null>(null)
  // The "Choose documents" sheet that starts every chat.
  const [sheetOpen, setSheetOpen] = useState(false)
  // With no chat yet the sheet opens by itself, once; closing it sticks.
  const [autoDismissed, setAutoDismissed] = useState(false)

  const isMobile = () => window.matchMedia(MOBILE_QUERY).matches

  const toggleSidebar = () => {
    if (isMobile()) {
      setMobileOpen((prev) => !prev)
      return
    }
    setCollapsed((prev) => {
      const next = !prev
      try {
        localStorage.setItem(COLLAPSED_KEY, String(next))
      } catch {
        // Storage may be disabled; the in-memory preference still works.
      }
      return next
    })
  }

  const go = (next: string) => {
    setView(next)
    setMobileOpen(false)
  }

  const autoPrompt =
    view === 'chat' &&
    !chat.initialLoading &&
    !chat.loading &&
    !filesLoading &&
    !chat.activeSession &&
    !autoDismissed

  const closeSheet = () => {
    setSheetOpen(false)
    setAutoDismissed(true)
  }

  const startChat = async (ids: string[]) => {
    await chat.newSession(ids)
    closeSheet()
  }

  const handleNewChat = () => {
    go('chat')
    setSheetOpen(true)
  }

  const goToDocuments = () => {
    closeSheet()
    go('files')
  }

  const handleSelect = (id: string) => {
    go('chat')
    void chat.selectSession(id)
  }

  const handleLogout = async () => {
    if (loggingOut) return
    setLoggingOut(true)
    setLogoutError(null)
    try {
      await logout()
      navigate('/', { replace: true })
    } catch (err) {
      setLogoutError(err instanceof Error ? err.message : 'Logout failed')
    } finally {
      setLoggingOut(false)
    }
  }

  const activePage = pages.find((p) => p.id === view)

  const sidebarToggle = (
    <button
      type="button"
      className="icon-btn"
      onClick={toggleSidebar}
      aria-label="Toggle sidebar"
      title="Toggle sidebar"
    >
      <SidebarIcon size={18} />
    </button>
  )

  return (
    <div className={`shell ${collapsed ? 'is-collapsed' : ''} ${mobileOpen ? 'is-mobile-open' : ''}`}>
      <aside className="shell__sidebar" aria-label="Sidebar">
        <div className="shell__sidebar-top">
          <Logo size="sm" />
          {sidebarToggle}
        </div>

        <nav className="shell__nav">
          <button type="button" className="shell__nav-item" onClick={handleNewChat}>
            <EditIcon size={16} />
            <span>New chat</span>
          </button>
          {pages.map((page) => (
            <button
              key={page.id}
              type="button"
              className={`shell__nav-item ${view === page.id ? 'is-active' : ''}`}
              onClick={() => go(page.id)}
            >
              {page.icon}
              <span>{page.label}</span>
            </button>
          ))}
        </nav>

        <div className="shell__history">
          <div className="shell__history-label">Chats</div>
          {chat.sessions.length === 0 ? (
            <p className="shell__history-empty">
              {chat.initialLoading ? 'Loading…' : 'No conversations yet'}
            </p>
          ) : (
            <ul className="shell__history-list">
              {chat.sessions.map((session) => {
                const isActive = view === 'chat' && session.id === chat.activeSession?.id
                return (
                  <li key={session.id} className={`shell__chat ${isActive ? 'is-active' : ''}`}>
                    <button
                      type="button"
                      className="shell__chat-title"
                      onClick={() => handleSelect(session.id)}
                      title={session.title}
                      aria-current={isActive ? 'page' : undefined}
                    >
                      <span className="shell__chat-text">{session.title}</span>
                    </button>
                    <button
                      type="button"
                      className="shell__chat-delete"
                      onClick={() => void chat.removeSession(session.id)}
                      aria-label={`Delete chat ${session.title}`}
                      title="Delete chat"
                    >
                      <TrashIcon size={14} />
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        <div className="shell__account">
          {logoutError && (
            <div className="shell__logout-error" role="alert">
              <span>{logoutError}</span>
              <button type="button" onClick={handleLogout} disabled={loggingOut}>
                Retry
              </button>
            </div>
          )}
          <div className="shell__account-row">
            <Avatar name={user.username} size="sm" variant={user.role === 'admin' ? 'accent' : 'neutral'} />
            <div className="shell__account-info">
              <span className="shell__account-name">{user.username}</span>
              <span className="shell__account-role">{user.role === 'admin' ? 'Admin' : 'Employee'}</span>
            </div>
            <button
              type="button"
              className="icon-btn"
              onClick={handleLogout}
              disabled={loggingOut}
              aria-label={loggingOut ? 'Logging out…' : 'Log out'}
              aria-busy={loggingOut}
              title="Log out"
            >
              <LogoutIcon size={16} />
            </button>
          </div>
        </div>
      </aside>

      {mobileOpen && (
        <div className="shell__scrim" onClick={() => setMobileOpen(false)} role="presentation" />
      )}

      <main className="shell__main">
        {activePage ? (
          <>
            <header className="shell__page-bar">
              <div className="shell__reveal">{sidebarToggle}</div>
            </header>
            <div className="shell__page">{activePage.content}</div>
          </>
        ) : (
          <ChatWindow
            leading={<div className="shell__reveal">{sidebarToggle}</div>}
            session={chat.activeSession}
            loading={chat.loading}
            error={chat.error}
            onDismissError={chat.dismissError}
            onReloadSession={chat.reloadSession}
            onSend={chat.send}
            onRegenerate={chat.regenerate}
            onClearHistory={chat.clearHistory}
            onNewChat={handleNewChat}
            accessibleFiles={accessibleFiles}
          />
        )}
      </main>

      <SourcesDialog
        open={sheetOpen || autoPrompt}
        files={accessibleFiles}
        onConfirm={startChat}
        onClose={closeSheet}
        onGoToDocuments={goToDocuments}
      />
    </div>
  )
}
