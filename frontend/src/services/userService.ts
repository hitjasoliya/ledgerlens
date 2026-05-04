import type { Role, SafeUser, User } from '../types'
import { uid } from '../lib/ids'
import { readJSON, StorageKeys, writeJSON } from '../lib/storage'
import { bus, Topics } from '../lib/eventBus'

const SEED_ADMIN: User = {
  id: '1',
  username: 'admin',
  password: 'admin123',
  role: 'admin',
  createdAt: Date.now(),
}

function toSafe(user: User): SafeUser {
  const { password: _password, ...rest } = user
  void _password
  return rest
}

let seeded = false

export function ensureSeed(): void {
  if (seeded) return
  const users = readJSON<User[]>(StorageKeys.users, [])
  if (users.length === 0) {
    writeJSON(StorageKeys.users, [SEED_ADMIN])
  }
  seeded = true
}

export function listUsers(): SafeUser[] {
  ensureSeed()
  return readJSON<User[]>(StorageKeys.users, []).map(toSafe)
}

export function listEmployees(): SafeUser[] {
  return listUsers().filter((u) => u.role === 'employee')
}

export function findById(id: string): SafeUser | null {
  ensureSeed()
  const u = readJSON<User[]>(StorageKeys.users, []).find((x) => x.id === id)
  return u ? toSafe(u) : null
}

export function authenticate(
  username: string,
  password: string,
  role: Role,
): SafeUser | null {
  ensureSeed()
  const users = readJSON<User[]>(StorageKeys.users, [])
  const match = users.find(
    (u) =>
      u.username.toLowerCase() === username.toLowerCase() &&
      u.password === password &&
      u.role === role,
  )
  return match ? toSafe(match) : null
}

export type CreateUserInput = {
  username: string
  password: string
  role: Role
  createdBy?: string
}

export function createUser(input: CreateUserInput): SafeUser {
  ensureSeed()
  const users = readJSON<User[]>(StorageKeys.users, [])
  const exists = users.some(
    (u) => u.username.toLowerCase() === input.username.toLowerCase(),
  )
  if (exists) throw new Error('Username already exists')
  if (!input.username.trim()) throw new Error('Username is required')
  if (input.password.length < 4) throw new Error('Password must be at least 4 characters')

  const newUser: User = {
    id: uid('user'),
    username: input.username.trim(),
    password: input.password,
    role: input.role,
    createdAt: Date.now(),
    createdBy: input.createdBy,
  }
  writeJSON(StorageKeys.users, [...users, newUser])
  bus.emit(Topics.users)
  return toSafe(newUser)
}

export function deleteUser(id: string): void {
  const users = readJSON<User[]>(StorageKeys.users, [])
  const filtered = users.filter((u) => u.id !== id)
  writeJSON(StorageKeys.users, filtered)
  bus.emit(Topics.users)
}
