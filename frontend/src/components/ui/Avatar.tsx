import { initials } from '../../lib/format'
import './Avatar.css'

type Props = {
  name: string
  size?: 'sm' | 'md' | 'lg'
  variant?: 'accent' | 'neutral'
}

export function Avatar({ name, size = 'md', variant = 'accent' }: Props) {
  return (
    <div className={`avatar avatar--${size} avatar--${variant}`} aria-label={name}>
      {initials(name)}
    </div>
  )
}
