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
): Promise<{ access_token: string; user: SafeUser }> {
  const res = await loginUser(username, password)
  return {
    access_token: res.access_token,
    user: res.user,
  }
}

export type CreateUserInput = {
  username: string
  password: string
  role: Role
}

export async function createUser(input: CreateUserInput): Promise<SafeUser> {
  const newUser = await saveUser({
    username: input.username.trim(),
    password: input.password,
    role: input.role,
  })
  bus.emit(Topics.users)
  return newUser
}

export async function deleteUser(id: string, transferTo?: string): Promise<void> {
  await removeUser(id, transferTo)
  bus.emit(Topics.users)
}
