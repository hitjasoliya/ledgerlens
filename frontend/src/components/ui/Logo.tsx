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
        <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path
            d="M16 3 L28 9 V20 C28 25 22 28.5 16 30 C10 28.5 4 25 4 20 V9 Z"
            fill="currentColor"
            opacity="0.92"
          />
          <path
            d="M11 14 L16 20 L21 14"
            stroke="#fff"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <circle cx="16" cy="11" r="1.6" fill="#fff" />
        </svg>
      </div>
      {showWordmark && (
        <span className="logo__wordmark">
          adani<span className="logo__accent">_rag</span>
        </span>
      )}
    </div>
  )
}
