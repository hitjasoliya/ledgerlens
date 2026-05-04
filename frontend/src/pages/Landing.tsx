import { Navigate, useNavigate } from 'react-router-dom'
import { Logo } from '../components/ui/Logo'
import { Button } from '../components/ui/Button'
import { ShieldIcon, UserIcon, ChevronRightIcon, SparklesIcon, FileIcon, MessageIcon } from '../components/ui/Icon'
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
      <header className="landing__header">
        <Logo size="md" />
        <nav className="landing__nav">
          <button
            type="button"
            className="landing__nav-link"
            onClick={() => navigate('/login?role=admin')}
          >
            Login
          </button>
        </nav>
      </header>

      <main className="landing__main">
        <section className="landing__hero">
          <div className="landing__badge">
            <SparklesIcon size={14} />
            <span>Enterprise RAG · Powered by Adani</span>
          </div>
          <h1 className="landing__title">
            Your documents,
            <br />
            <span className="landing__title-accent">intelligently answered.</span>
          </h1>
          <p className="landing__subtitle">
            adani_rag transforms your enterprise documents into a conversational
            knowledge base. Upload, control access, and ask anything — with
            page-level citations grounded in your data.
          </p>

          <div className="landing__cta">
            <Button
              size="lg"
              variant="primary"
              onClick={() => navigate('/login?role=admin')}
              rightIcon={<ChevronRightIcon size={16} />}
              leftIcon={<ShieldIcon size={16} />}
            >
              Login as Admin
            </Button>
            <Button
              size="lg"
              variant="secondary"
              onClick={() => navigate('/login?role=employee')}
              rightIcon={<ChevronRightIcon size={16} />}
              leftIcon={<UserIcon size={16} />}
            >
              Login as Employee
            </Button>
          </div>

          <p className="landing__hint">
            Default admin: <code>admin</code> / <code>admin123</code>
          </p>
        </section>

        <section className="landing__features">
          <FeatureCard
            icon={<FileIcon size={20} />}
            title="Granular access control"
            description="Admins curate the knowledge base and decide which employees can query each document."
          />
          <FeatureCard
            icon={<MessageIcon size={20} />}
            title="Cited conversations"
            description="Every answer ships with page-level citations so trust is built into the response."
          />
          <FeatureCard
            icon={<SparklesIcon size={20} />}
            title="Personal context"
            description="Employees can attach their own documents to a chat for ad-hoc analysis."
          />
        </section>
      </main>

      <footer className="landing__footer">
        <span>© {new Date().getFullYear()} adani_rag</span>
        <span className="landing__footer-dot">·</span>
        <span>Built for enterprise knowledge teams</span>
      </footer>

      <div className="landing__glow" aria-hidden />
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
