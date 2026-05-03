import { useState, useEffect } from 'react'
import ChatPanel from './components/ChatPanel'
import IngestPanel from './components/IngestPanel'
import { endSession } from './api'
import './App.css'

function App() {
  const [role, setRole] = useState<'user' | 'admin'>('user')
  const [userId, setUserId] = useState('user_' + Math.floor(Math.random() * 10000))
  const [sessionId, setSessionId] = useState('sess_' + Math.floor(Math.random() * 1000000))

  const handleEndSession = async () => {
    try {
      await endSession(sessionId)
      // generate new session id so they start fresh
      setSessionId('sess_' + Math.floor(Math.random() * 1000000))
      alert('Session Ended! Temporary PDFs destroyed.')
    } catch (e) {
      console.error(e)
      alert('Failed to end session')
    }
  }

  const handleRoleChange = (newRole: 'user' | 'admin') => {
    setRole(newRole)
    // Completely reset identity to simulate switching to a different computer/user
    setUserId(newRole + '_' + Math.floor(Math.random() * 10000))
    setSessionId('sess_' + Math.floor(Math.random() * 1000000))
  }

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <path d="M12 16v-4" />
              <path d="M12 8h.01" />
            </svg>
          </div>
          <div>
            <h1 className="brand-title">KingSlayer</h1>
            <p className="brand-sub">RAG Document Q&A</p>
          </div>
        </div>

        <div style={{ padding: '15px 20px', borderBottom: '1px solid #333', marginBottom: '15px' }}>
          <h3 style={{ fontSize: '12px', color: '#888', marginBottom: '8px', textTransform: 'uppercase' }}>Current Role</h3>
          <select 
            value={role} 
            onChange={e => handleRoleChange(e.target.value as any)}
            style={{ width: '100%', padding: '8px', borderRadius: '6px', background: '#222', color: '#fff', border: '1px solid #444', marginBottom: '8px' }}
          >
            <option value="user">Normal User</option>
            <option value="admin">Admin</option>
          </select>
          <div style={{ fontSize: '12px', color: '#aaa', fontFamily: 'monospace' }}>
            ID: {userId} <br/>
            Session: {sessionId}
          </div>
        </div>

        <IngestPanel role={role} userId={userId} sessionId={sessionId} />

        <div className="sidebar-footer">
          <button 
            onClick={() => void handleEndSession()}
            style={{ width: '100%', padding: '10px', background: 'rgba(255,50,50,0.1)', color: '#ff6b6b', border: '1px solid rgba(255,50,50,0.2)', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold' }}
          >
            End Session & Cleanup
          </button>
        </div>
      </aside>

      <main className="chat-main">
        <ChatPanel userId={userId} sessionId={sessionId} />
      </main>
    </div>
  )
}

export default App
