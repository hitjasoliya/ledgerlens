import { initials } from '../../lib/format'
import './Avatar.css'

type Props = {
  name: string
  size?: 'sm' | 'md' | 'lg'
  variant?: 'coral' | 'dark' | 'soft'
}

export function Avatar({ name, size = 'md', variant = 'coral' }: Props) {
  return (
    <div className={`avatar avatar--${size} avatar--${variant}`} aria-label={name}>
      {initials(name)}
    </div>
  )
}
