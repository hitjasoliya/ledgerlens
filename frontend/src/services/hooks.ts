import { useMemo, useSyncExternalStore } from 'react'
import type { FileEntry, SafeUser } from '../types'
import { bus, Topics } from '../lib/eventBus'
import {
  listAdminFiles,
  listAllFiles,
  listFilesAccessibleTo,
  listFilesOwnedBy,
} from './fileService'
import { listEmployees, listUsers } from './userService'

type CacheRecord<T> = { value: T; signature: string } | null
const snapshotCache = new Map<string, CacheRecord<unknown>>()

function readSnapshot<T>(cacheKey: string, loader: () => T): T {
  const next = loader()
  const signature = JSON.stringify(next)
  const existing = snapshotCache.get(cacheKey) as CacheRecord<T>
  if (existing && existing.signature === signature) {
    return existing.value
  }
  snapshotCache.set(cacheKey, { value: next, signature })
  return next
}

function makeStore<T>(topic: string, cacheKey: string, loader: () => T) {
  const subscribe = (listener: () => void) =>
    bus.subscribe(topic, () => {
      snapshotCache.delete(cacheKey)
      listener()
    })
  const snapshot = () => readSnapshot<T>(cacheKey, loader)
  return { subscribe, snapshot }
}

function useReactive<T>(topic: string, cacheKey: string, loader: () => T): T {
  const { subscribe, snapshot } = useMemo(
    () => makeStore<T>(topic, cacheKey, loader),
    [topic, cacheKey, loader],
  )
  return useSyncExternalStore(subscribe, snapshot, snapshot)
}

export function useUsers(): SafeUser[] {
  return useReactive<SafeUser[]>(Topics.users, 'users:all', listUsers)
}

export function useEmployees(): SafeUser[] {
  return useReactive<SafeUser[]>(Topics.users, 'users:employees', listEmployees)
}

export function useAllFiles(): FileEntry[] {
  return useReactive<FileEntry[]>(Topics.files, 'files:all', listAllFiles)
}

export function useAdminFiles(): FileEntry[] {
  return useReactive<FileEntry[]>(Topics.files, 'files:admin', listAdminFiles)
}

export function useAccessibleFiles(userId: string): FileEntry[] {
  const loader = useMemo(() => () => listFilesAccessibleTo(userId), [userId])
  return useReactive<FileEntry[]>(Topics.files, `files:accessible:${userId}`, loader)
}

export function useOwnFiles(userId: string): FileEntry[] {
  const loader = useMemo(() => () => listFilesOwnedBy(userId), [userId])
  return useReactive<FileEntry[]>(Topics.files, `files:own:${userId}`, loader)
}
