import { useId } from 'react'
import type { InputHTMLAttributes } from 'react'
import './Input.css'

type Props = InputHTMLAttributes<HTMLInputElement> & {
  label?: string
  error?: string
  hint?: string
}

export function Input({ label, error, hint, className = '', id, ...rest }: Props) {
  const reactId = useId()
  const inputId = id ?? rest.name ?? reactId
  return (
    <div className={`field ${error ? 'field--error' : ''}`}>
      {label && (
        <label className="field__label" htmlFor={inputId}>
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={`field__input ${className}`}
        {...rest}
      />
      {(error || hint) && (
        <p className={`field__hint ${error ? 'field__hint--error' : ''}`}>
          {error ?? hint}
        </p>
      )}
    </div>
  )
}
