type Listener = () => void

class EventBus {
  private listeners = new Map<string, Set<Listener>>()

  subscribe(topic: string, listener: Listener): () => void {
    let set = this.listeners.get(topic)
    if (!set) {
      set = new Set()
      this.listeners.set(topic, set)
    }
    set.add(listener)
    return () => {
      set!.delete(listener)
      if (set!.size === 0) this.listeners.delete(topic)
    }
  }

  emit(topic: string): void {
    const set = this.listeners.get(topic)
    if (!set) return
    for (const listener of set) {
      try {
        listener()
      } catch {
        /* listener errors are non-fatal */
      }
    }
  }
}

export const bus = new EventBus()

export const Topics = {
  users: 'users',
  files: 'files',
  chats: (ownerId: string) => `chats:${ownerId}`,
} as const
