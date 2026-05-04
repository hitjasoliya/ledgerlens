const NAMESPACE = 'adani_rag'

export const StorageKeys = {
  users: `${NAMESPACE}.users`,
  session: `${NAMESPACE}.session`,
  files: `${NAMESPACE}.files`,
  chats: (userId: string) => `${NAMESPACE}.chats.${userId}`,
  sessionFiles: (sessionId: string) => `${NAMESPACE}.session_files.${sessionId}`,
} as const

export function readJSON<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return fallback
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

export function writeJSON<T>(key: string, value: T): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* quota or serialization errors are non-fatal */
  }
}

export function removeKey(key: string): void {
  try {
    localStorage.removeItem(key)
  } catch {
    /* noop */
  }
}

export function readSessionJSON<T>(key: string, fallback: T): T {
  try {
    const raw = sessionStorage.getItem(key)
    if (!raw) return fallback
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

export function writeSessionJSON<T>(key: string, value: T): void {
  try {
    sessionStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* noop */
  }
}

export function removeSessionKey(key: string): void {
  try {
    sessionStorage.removeItem(key)
  } catch {
    /* noop */
  }
}
