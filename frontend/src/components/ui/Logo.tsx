import './Logo.css'

type Props = {
  size?: 'sm' | 'md' | 'lg'
  variant?: 'light' | 'dark'
  showWordmark?: boolean
}

export function Logo({ size = 'md', variant = 'light', showWordmark = true }: Props) {
  return (
    <div className={`logo logo--${size} logo--${variant}`}>
      <div className="logo__mark" aria-hidden>
        <svg viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg">
          {/* Cash note */}
          <rect
            x="3" y="6" width="30" height="24" rx="1.5"
            stroke="currentColor"
            strokeWidth="2"
            fill="none"
          />
          {/* Folded corner */}
          <path
            d="M27 6L33 12V12.5"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
          />
          {/* Currency symbol */}
          <text
            x="18" y="22"
            textAnchor="middle"
            fontSize="14"
            fontFamily="monospace"
            fontWeight="700"
            fill="currentColor"
          >
            $
          </text>
        </svg>
      </div>
      {showWordmark && (
        <span className="logo__wordmark">
          Ledger<span className="logo__accent">Lens</span>
        </span>
      )}
    </div>
  )
}
