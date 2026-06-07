import type { Role, SafeUser } from '../types'
import { fetchUsers, saveUser, removeUser, loginUser } from '../lib/api'
import { bus, Topics } from '../lib/eventBus'

export function ensureSeed(): void {
  // Backend database seeds itself on startup.
}

export async function listUsers(): Promise<SafeUser[]> {
  try {
    return await fetchUsers()
  } catch (e) {
    console.error("Failed to list users", e)
    return []
  }
}

export async function listEmployees(): Promise<SafeUser[]> {
  const users = await listUsers()
  return users.filter((u) => u.role === 'employee')
}

export async function findById(id: string): Promise<SafeUser | null> {
  const users = await listUsers()
  return users.find((x) => x.id === id) ?? null
}

export async function authenticate(
  username: string,
  password: string,
  role: Role,
): Promise<{ access_token: string; user: SafeUser } | null> {
  try {
    const res = await loginUser(username, password, role)
    return {
      access_token: res.access_token,
      user: res.user as SafeUser
    }
  } catch (e) {
    console.error("Authentication failed", e)
    return null
  }
}

export type CreateUserInput = {
  username: string
  password: string
  role: Role
  createdBy?: string
}

export async function createUser(input: CreateUserInput): Promise<SafeUser> {
  const newUser = await saveUser({
    username: input.username.trim(),
    password: input.password,
    role: input.role,
  })
  bus.emit(Topics.users)
  return newUser as SafeUser
}

export async function deleteUser(id: string): Promise<void> {
  await removeUser(id)
  bus.emit(Topics.users)
}
