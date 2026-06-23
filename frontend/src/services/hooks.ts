import { useState, useEffect } from 'react'
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
    let active = true
    const load = async () => {
      const data = await listUsers()
      if (active) setUsers(data)
    }
    load()
    return bus.subscribe(Topics.users, load)
  }, [])

  return users
}

export function useEmployees(): SafeUser[] {
  const [employees, setEmployees] = useState<SafeUser[]>([])

  useEffect(() => {
    let active = true
    const load = async () => {
      const data = await listEmployees()
      if (active) setEmployees(data)
    }
    load()
    return bus.subscribe(Topics.users, load)
  }, [])

  return employees
}

export function useAllFiles(): FileEntry[] {
  const [files, setFiles] = useState<FileEntry[]>([])

  useEffect(() => {
    let active = true
    const load = async () => {
      const data = await listAllFiles()
      if (active) setFiles(data)
    }
    load()
    return bus.subscribe(Topics.files, load)
  }, [])

  return files
}

export function useAdminFiles(): FileEntry[] {
  const [files, setFiles] = useState<FileEntry[]>([])

  useEffect(() => {
    let active = true
    const load = async () => {
      const data = await listAdminFiles()
      if (active) setFiles(data)
    }
    load()
    return bus.subscribe(Topics.files, load)
  }, [])

  return files
}

export function useAccessibleFiles(userId: string): FileEntry[] {
  const [files, setFiles] = useState<FileEntry[]>([])

  useEffect(() => {
    if (!userId) return
    let active = true
    const load = async () => {
      const data = await listFilesAccessibleTo(userId)
      if (active) setFiles(data)
    }
    load()
    return bus.subscribe(Topics.files, load)
  }, [userId])

  return files
}

export function useOwnFiles(userId: string): FileEntry[] {
  const [files, setFiles] = useState<FileEntry[]>([])

  useEffect(() => {
    if (!userId) return
    let active = true
    const load = async () => {
      const data = await listFilesOwnedBy(userId)
      if (active) setFiles(data)
    }
    load()
    return bus.subscribe(Topics.files, load)
  }, [userId])

  return files
}
