import { Navigate, useNavigate } from 'react-router-dom'
import { Logo } from '../components/ui/Logo'
import { Button } from '../components/ui/Button'
import { ArrowUpIcon, FileIcon, LockIcon, PaperclipIcon } from '../components/ui/Icon'
import { useAuth } from '../auth/useAuth'
import './Landing.css'

const STEPS = [
  {
    title: 'Upload PDFs',
    body: 'Annual reports, filings, board packs. Text and tables are parsed and indexed for search.',
  },
  {
    title: 'Choose the sources',
    body: 'Pick which documents a chat may use. After the first question, that choice is locked for the chat.',
  },
  {
    title: 'Ask, then verify',
    body: 'Each claim carries a numbered marker. Click it to open the PDF at the cited page.',
  },
]

const FEATURES = [
  { title: 'Page-level citations', body: 'Every supported answer points to the document and page it came from.' },
  { title: 'No answer beats a wrong one', body: 'When the evidence isn’t there, it says so instead of guessing.' },
  { title: 'Reads tables', body: 'Figures from tables are retrieved alongside the surrounding text.' },
  { title: 'Fixed sources per chat', body: 'A conversation can’t quietly change the documents it answers from.' },
  { title: 'Private by default', body: 'Personal uploads stay yours unless an administrator shares them.' },
  { title: 'Admin-controlled sharing', body: 'Admins decide which employees can ask about each document.' },
]

export function Landing() {
  const navigate = useNavigate()
  const { user } = useAuth()

  if (user) {
    return <Navigate to={user.role === 'admin' ? '/admin' : '/employee'} replace />
  }

  const start = () => navigate('/login')

  return (
    <div className="landing">
      <header className="landing__nav">
        <Logo size="sm" />
        <nav className="landing__links" aria-label="Sections">
          <a href="#how">How it works</a>
          <a href="#trust">Why trust it</a>
          <a href="#features">Features</a>
        </nav>
        <Button size="sm" variant="secondary" onClick={start}>
          Log in
        </Button>
      </header>

      <main>
        {/* ---------- Hero ---------- */}
        <section className="hero">
          <span className="hero__eyebrow">Document Q&amp;A for finance teams</span>
          <h1 className="hero__title">
            Ask your filings.
            <br />
            <span className="hero__title-muted">Check every answer.</span>
          </h1>
          <p className="hero__subtitle">
            LedgerLens answers questions from your PDFs and cites the exact page for every figure, so
            you can confirm it in seconds.
          </p>
          <div className="hero__cta">
            <Button size="lg" variant="primary" onClick={start}>
              Get started
            </Button>
            <a className="hero__secondary" href="#how">
              See how it works
            </a>
          </div>

          <div className="mock" aria-hidden>
            <div className="mock__chrome">
              <span />
              <span />
              <span />
            </div>
            <div className="mock__body">
              <div className="mock__q">What was Contoso’s net loss in Q3 2025?</div>
              <div className="mock__a">
                Contoso reported a net loss of <strong>€2.94 million</strong> in Q3 2025, wider than
                the €1.66 million loss a year earlier
                <span className="mock__cite">1</span>. R&amp;D spending rose by €2.62 million to
                €15.64 million<span className="mock__cite">1</span>.
              </div>
              <div className="mock__sources">
                <span className="mock__chip">
                  <span className="mock__chip-n">1</span>
                  contoso_q3_2025_quarterly_report
                  <span className="mock__chip-page">p. 1</span>
                </span>
              </div>
              <div className="mock__composer">
                <PaperclipIcon size={15} />
                <span className="mock__pill">
                  <LockIcon size={11} /> 1 source
                </span>
                <span className="mock__placeholder">Ask a follow-up</span>
                <span className="mock__send">
                  <ArrowUpIcon size={14} />
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* ---------- How it works ---------- */}
        <section className="section" id="how">
          <p className="section__kicker">How it works</p>
          <h2 className="section__title">Three steps from PDF to a cited answer.</h2>
          <ol className="steps">
            {STEPS.map((step, i) => (
              <li key={step.title} className="steps__item">
                <span className="steps__n">{String(i + 1).padStart(2, '0')}</span>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </li>
            ))}
          </ol>
        </section>

        {/* ---------- Trust ---------- */}
        <section className="section split" id="trust">
          <div className="split__text">
            <p className="section__kicker">Why trust it</p>
            <h2 className="section__title">It tells you when the answer isn’t there.</h2>
            <p className="section__body">
              If the selected documents don’t support an answer, LedgerLens says so rather than filling
              the gap with a plausible number. An answer that cites a passage it was never given is
              rejected before you see it.
            </p>
          </div>
          <div className="split__card" aria-hidden>
            <div className="mock__q">What is Contoso’s total debt?</div>
            <div className="mock__a mock__a--abstain">
              The selected document doesn’t state Contoso’s total debt. It reports cash of €92.4
              million and the quarterly results, but no borrowings figure.
            </div>
            <div className="split__note">
              <FileIcon size={13} />
              Searched 1 selected document
            </div>
          </div>
        </section>

        {/* ---------- Features ---------- */}
        <section className="section" id="features">
          <p className="section__kicker">Features</p>
          <h2 className="section__title">Built for numbers people have to defend.</h2>
          <ul className="features">
            {FEATURES.map((f) => (
              <li key={f.title}>
                <h3>{f.title}</h3>
                <p>{f.body}</p>
              </li>
            ))}
          </ul>
        </section>

        {/* ---------- Closing CTA ---------- */}
        <section className="closing">
          <h2>Start with one PDF.</h2>
          <p>Upload a report and ask the question you’d otherwise search for by hand.</p>
          <Button size="lg" variant="primary" onClick={start}>
            Get started
          </Button>
        </section>
      </main>

      <footer className="landing__footer">
        <Logo size="sm" />
        <span>© {new Date().getFullYear()} LedgerLens</span>
      </footer>
    </div>
  )
}
