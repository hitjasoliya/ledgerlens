import type { ButtonHTMLAttributes, ReactNode } from 'react'
import './Button.css'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'dark'
type Size = 'sm' | 'md' | 'lg'

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant
  size?: Size
  loading?: boolean
  leftIcon?: ReactNode
  rightIcon?: ReactNode
  fullWidth?: boolean
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  leftIcon,
  rightIcon,
  fullWidth = false,
  disabled,
  children,
  className = '',
  type = 'button',
  ...rest
}: Props) {
  const classes = [
    'btn',
    `btn--${variant}`,
    `btn--${size}`,
    fullWidth ? 'btn--full' : '',
    loading ? 'btn--loading' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button
      type={type}
      className={classes}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? <span className="btn__spinner" aria-hidden /> : leftIcon}
      <span className="btn__label">{children}</span>
      {!loading && rightIcon}
    </button>
  )
}
