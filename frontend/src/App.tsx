import ChatPanel from './components/ChatPanel'
import IngestPanel from './components/IngestPanel'
import './App.css'

function App() {
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

        <IngestPanel />

        <div className="sidebar-footer">
          <span>Powered by RAG Pipeline</span>
        </div>
      </aside>

      <main className="chat-main">
        <ChatPanel />
      </main>
    </div>
  )
}

export default App
