export function uid(prefix = 'id'): string {
  const rand = Math.random().toString(36).slice(2, 10)
  return `${prefix}_${Date.now().toString(36)}_${rand}`
}

export function shortId(): string {
  return Math.random().toString(36).slice(2, 8)
}
