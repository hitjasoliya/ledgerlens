import './Logo.css'

type Props = {
  size?: 'sm' | 'md' | 'lg'
  showWordmark?: boolean
}

export function Logo({ size = 'md', showWordmark = true }: Props) {
  return (
    <div className={`logo logo--${size}`}>
      <span className="logo__mark" aria-hidden>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="10.5" cy="10.5" r="6" />
          <line x1="15" y1="15" x2="20" y2="20" />
        </svg>
      </span>
      {showWordmark && <span className="logo__wordmark">LedgerLens</span>}
    </div>
  )
}
