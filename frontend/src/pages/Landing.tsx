import { Navigate, useNavigate } from 'react-router-dom'
import { Logo } from '../components/ui/Logo'
import { Button } from '../components/ui/Button'
import { ChevronRightIcon, FileIcon, MessageIcon, SparklesIcon } from '../components/ui/Icon'
import { useAuth } from '../auth/useAuth'
import './Landing.css'

export function Landing() {
  const navigate = useNavigate()
  const { user } = useAuth()

  if (user) {
    return <Navigate to={user.role === 'admin' ? '/admin' : '/employee'} replace />
  }

  return (
    <div className="landing">
      <div className="landing__scanline" aria-hidden />

      <header className="landing__header">
        <Logo size="md" />
        <nav>
          <button
            type="button"
            className="landing__nav-link"
            onClick={() => navigate('/login?role=admin')}
          >
            login
          </button>
        </nav>
      </header>

      <main className="landing__main">
        <section className="landing__hero">
          <div className="landing__prompt">
            <span>&gt; LedgerLens.init()</span>
            <span className="landing__prompt-cursor" />
          </div>

          <h1 className="landing__title">
            Query your documents.
            <br />
            <span className="landing__title-accent">Get cited answers.</span>
          </h1>

          <p className="landing__subtitle">
            Upload enterprise PDFs. Ask questions in natural language.
            Get responses grounded in your data with page-level citations.
            No hallucinations. Just facts.
          </p>

          <div className="landing__cta">
            <Button
              size="lg"
              variant="primary"
              onClick={() => navigate('/login?role=admin')}
              rightIcon={<ChevronRightIcon size={14} />}
            >
              Login as Admin
            </Button>
            <Button
              size="lg"
              variant="secondary"
              onClick={() => navigate('/login?role=employee')}
              rightIcon={<ChevronRightIcon size={14} />}
            >
              Login as Employee
            </Button>
          </div>

          <p className="landing__hint">
            defaults: <code>admin</code> / <code>admin123</code>
          </p>
        </section>

        <section className="landing__features">
          <FeatureCard
            icon={<FileIcon size={18} />}
            title="Access Control"
            description="Admins curate the knowledge base. Decide which employees can query each document."
          />
          <FeatureCard
            icon={<MessageIcon size={18} />}
            title="Cited Answers"
            description="Every response includes page-level citations grounded in your documents."
          />
          <FeatureCard
            icon={<SparklesIcon size={18} />}
            title="Ad-hoc Analysis"
            description="Attach your own PDFs to any conversation for instant analysis."
          />
        </section>
      </main>

      <footer className="landing__footer">
        <span>&copy; {new Date().getFullYear()} LedgerLens</span>
        <span className="landing__footer-dot">·</span>
        <span>Enterprise RAG Platform</span>
      </footer>
    </div>
  )
}

function FeatureCard({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode
  title: string
  description: string
}) {
  return (
    <div className="feature-card">
      <div className="feature-card__icon">{icon}</div>
      <h3 className="feature-card__title">{title}</h3>
      <p className="feature-card__desc">{description}</p>
    </div>
  )
}
