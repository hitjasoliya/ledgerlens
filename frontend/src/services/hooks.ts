import { useState, useEffect, useCallback } from 'react'
import type { FileEntry, SafeUser } from '../types'
import { bus, Topics } from '../lib/eventBus'
import {
  listAdminFiles,
  listAllFiles,
  listFilesAccessibleTo,
  listFilesOwnedBy,
} from './fileService'
import { listEmployees, listUsers } from './userService'

export function useUsers(): SafeUser[] {
  const [users, setUsers] = useState<SafeUser[]>([])

  useEffect(() => {
    const controller = new AbortController()

    listUsers()
      .then((data) => {
        if (!controller.signal.aborted) setUsers(data)
      })
      .catch(() => {
        if (!controller.signal.aborted) setUsers([])
      })

    const unsubscribe = bus.subscribe(Topics.users, () => {
      listUsers()
        .then((data) => {
          if (!controller.signal.aborted) setUsers(data)
        })
        .catch(() => {})
    })

    return () => {
      controller.abort()
      unsubscribe()
    }
  }, [])

  return users
}

export function useEmployees(): SafeUser[] {
  const [employees, setEmployees] = useState<SafeUser[]>([])

  useEffect(() => {
    const controller = new AbortController()

    listEmployees()
      .then((data) => {
        if (!controller.signal.aborted) setEmployees(data)
      })
      .catch(() => {
        if (!controller.signal.aborted) setEmployees([])
      })

    const unsubscribe = bus.subscribe(Topics.users, () => {
      listEmployees()
        .then((data) => {
          if (!controller.signal.aborted) setEmployees(data)
        })
        .catch(() => {})
    })

    return () => {
      controller.abort()
      unsubscribe()
    }
  }, [])

  return employees
}

export type FilesState = {
  files: FileEntry[]
  loading: boolean
  error: string | null
  reload: () => void
}

export function useAllFilesState(): FilesState {
  const [files, setFiles] = useState<FileEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    listAllFiles()
      .then((data) => {
        if (!controller.signal.aborted) {
          setFiles(data)
          setError(null)
          setLoading(false)
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : String(err))
          setFiles([])
          setLoading(false)
        }
      })

    const unsubscribe = bus.subscribe(Topics.files, () => {
      listAllFiles()
        .then((data) => {
          if (!controller.signal.aborted) {
            setFiles(data)
            setError(null)
          }
        })
        .catch((err) => {
          if (!controller.signal.aborted) {
            setError(err instanceof Error ? err.message : String(err))
          }
        })
    })

    return () => {
      controller.abort()
      unsubscribe()
    }
  }, [])

  const reload = useCallback(() => {
    setLoading(true)
    setError(null)
    listAllFiles()
      .then((data) => {
        setFiles(data)
        setError(null)
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err))
        setFiles([])
      })
      .finally(() => {
        setLoading(false)
      })
  }, [])

  return { files, loading, error, reload }
}

export function useAllFiles(): FileEntry[] {
  const { files } = useAllFilesState()
  return files
}

export function useAdminFilesState(): FilesState {
  const [files, setFiles] = useState<FileEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    listAdminFiles()
      .then((data) => {
        if (!controller.signal.aborted) {
          setFiles(data)
          setError(null)
          setLoading(false)
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : String(err))
          setFiles([])
          setLoading(false)
        }
      })

    const unsubscribe = bus.subscribe(Topics.files, () => {
      listAdminFiles()
        .then((data) => {
          if (!controller.signal.aborted) {
            setFiles(data)
            setError(null)
          }
        })
        .catch((err) => {
          if (!controller.signal.aborted) {
            setError(err instanceof Error ? err.message : String(err))
          }
        })
    })

    return () => {
      controller.abort()
      unsubscribe()
    }
  }, [])

  const reload = useCallback(() => {
    setLoading(true)
    setError(null)
    listAdminFiles()
      .then((data) => {
        setFiles(data)
        setError(null)
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err))
        setFiles([])
      })
      .finally(() => {
        setLoading(false)
      })
  }, [])

  return { files, loading, error, reload }
}

export function useAdminFiles(): FileEntry[] {
  const { files } = useAdminFilesState()
  return files
}

export function useAccessibleFilesState(userId: string): FilesState {
  const [files, setFiles] = useState<FileEntry[]>([])
  const [loading, setLoading] = useState(Boolean(userId))
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!userId) {
      return
    }
    const controller = new AbortController()

    listFilesAccessibleTo(userId)
      .then((data) => {
        if (!controller.signal.aborted) {
          setFiles(data)
          setError(null)
          setLoading(false)
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : String(err))
          setFiles([])
          setLoading(false)
        }
      })

    const unsubscribe = bus.subscribe(Topics.files, () => {
      listFilesAccessibleTo(userId)
        .then((data) => {
          if (!controller.signal.aborted) {
            setFiles(data)
            setError(null)
          }
        })
        .catch((err) => {
          if (!controller.signal.aborted) {
            setError(err instanceof Error ? err.message : String(err))
          }
        })
    })

    return () => {
      controller.abort()
      unsubscribe()
    }
  }, [userId])

  const reload = useCallback(() => {
    if (!userId) return
    setLoading(true)
    setError(null)
    listFilesAccessibleTo(userId)
      .then((data) => {
        setFiles(data)
        setError(null)
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err))
        setFiles([])
      })
      .finally(() => {
        setLoading(false)
      })
  }, [userId])

  return { files, loading, error, reload }
}

export function useAccessibleFiles(userId: string): FileEntry[] {
  const { files } = useAccessibleFilesState(userId)
  return files
}

export function useOwnFilesState(userId: string): FilesState {
  const [files, setFiles] = useState<FileEntry[]>([])
  const [loading, setLoading] = useState(Boolean(userId))
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!userId) {
      return
    }
    const controller = new AbortController()

    listFilesOwnedBy(userId)
      .then((data) => {
        if (!controller.signal.aborted) {
          setFiles(data)
          setError(null)
          setLoading(false)
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : String(err))
          setFiles([])
          setLoading(false)
        }
      })

    const unsubscribe = bus.subscribe(Topics.files, () => {
      listFilesOwnedBy(userId)
        .then((data) => {
          if (!controller.signal.aborted) {
            setFiles(data)
            setError(null)
          }
        })
        .catch((err) => {
          if (!controller.signal.aborted) {
            setError(err instanceof Error ? err.message : String(err))
          }
        })
    })

    return () => {
      controller.abort()
      unsubscribe()
    }
  }, [userId])

  const reload = useCallback(() => {
    if (!userId) return
    setLoading(true)
    setError(null)
    listFilesOwnedBy(userId)
      .then((data) => {
        setFiles(data)
        setError(null)
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err))
        setFiles([])
      })
      .finally(() => {
        setLoading(false)
      })
  }, [userId])

  return { files, loading, error, reload }
}

export function useOwnFiles(userId: string): FileEntry[] {
  const { files } = useOwnFilesState(userId)
  return files
}
