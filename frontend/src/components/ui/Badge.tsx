import type { ReactNode } from 'react'
import './Badge.css'

type Props = {
  children: ReactNode
  tone?: 'neutral' | 'accent' | 'success' | 'danger' | 'dark'
  size?: 'sm' | 'md'
}

export function Badge({ children, tone = 'neutral', size = 'sm' }: Props) {
  return <span className={`badge badge--${tone} badge--${size}`}>{children}</span>
}
