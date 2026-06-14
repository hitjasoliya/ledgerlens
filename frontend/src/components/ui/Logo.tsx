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
        <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
          {/* Outer hexagon — structure / precision */}
          <path
            d="M20 2L36 11V29L20 38L4 29V11L20 2Z"
            stroke="currentColor"
            strokeWidth="1.8"
            fill="none"
          />
          {/* Inner hexagon — data / core */}
          <path
            d="M20 8L29 13.5V24.5L20 30L11 24.5V13.5L20 8Z"
            stroke="currentColor"
            strokeWidth="1.2"
            fill="none"
            opacity="0.5"
          />
          {/* C — query lens */}
          <path
            d="M18 14C15.8 14 14 15.8 14 18V22C14 24.2 15.8 26 18 26"
            stroke="currentColor"
            strokeWidth="2.8"
            strokeLinecap="round"
            fill="none"
          />
          {/* Q tail / pulse — the insight coming out */}
          <line
            x1="22" y1="22"
            x2="27" y2="27"
            stroke="currentColor"
            strokeWidth="2.8"
            strokeLinecap="round"
          />
          {/* Accent dot — data point */}
          <circle cx="27" cy="27" r="2" fill="currentColor" />
          {/* Small accent dot */}
          <circle cx="13" cy="13" r="1.5" fill="currentColor" opacity="0.4" />
        </svg>
      </div>
      {showWordmark && (
        <span className="logo__wordmark">
          Capital<span className="logo__accent">Query</span>
        </span>
      )}
    </div>
  )
}
