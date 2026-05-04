import { useCallback, useMemo, useState } from 'react'
import type { FileEntry, SafeUser } from '../../types'
import { ChatSidebar } from './ChatSidebar'
import { ChatWindow } from './ChatWindow'
import { useChat } from './useChat'
import { ingestPdf } from '../../lib/api'
import { createFile, findFile } from '../../services/fileService'
import { writeSessionJSON, StorageKeys, readSessionJSON } from '../../lib/storage'
import './ChatShell.css'

type Props = {
  user: SafeUser
  accessibleFiles: FileEntry[]
  allowFileAttach: boolean
  fileScope: 'admin' | 'employee'
}

type EphemeralFileMeta = {
  filename: string
  uploadedAt: number
}

export function ChatShell({ user, accessibleFiles, allowFileAttach, fileScope }: Props) {
  const chat = useChat({ ownerId: user.id })
  const [attaching, setAttaching] = useState(false)

  const contextFile = useMemo<FileEntry | null>(() => {
    if (!chat.activeSession?.contextFileId) return null
    return findFile(chat.activeSession.contextFileId)
  }, [chat.activeSession])

  const handleSend = useCallback(
    async (text: string, file?: File) => {
      if (!chat.activeSession) return
      let attachedEntry: FileEntry | undefined

      if (file) {
        setAttaching(true)
        try {
          const result = await ingestPdf({
            file,
            userId: user.id,
            sessionId: chat.activeSession.id,
            isPersistent: fileScope === 'employee' ? true : false,
            allowedUsers: fileScope === 'employee' ? [user.id] : [],
          })

          if (fileScope === 'employee') {
            attachedEntry = createFile({
              filename: file.name,
              source: result.source,
              uploadedBy: user.username,
              uploadedById: user.id,
              scope: 'employee',
              accessList: [user.id],
              pagesParsed: result.pages_parsed,
              chunksCreated: result.chunks_created,
              chunksIndexed: result.chunks_indexed,
              isPersistent: true,
              sessionId: chat.activeSession.id,
            })
          } else {
            const key = StorageKeys.sessionFiles(chat.activeSession.id)
            const existing = readSessionJSON<EphemeralFileMeta[]>(key, [])
            writeSessionJSON(key, [
              ...existing,
              { filename: file.name, uploadedAt: Date.now() },
            ])
          }
        } catch (err) {
          alert(`Upload failed: ${err instanceof Error ? err.message : String(err)}`)
          setAttaching(false)
          return
        }
        setAttaching(false)
      }

      await chat.send(text, attachedEntry)
    },
    [chat, user, fileScope],
  )

  return (
    <div className="chat-shell">
      <ChatSidebar
        sessions={chat.sessions}
        activeId={chat.activeSession?.id ?? null}
        onSelect={chat.selectSession}
        onNew={chat.newSession}
        onDelete={chat.removeSession}
      />
      <ChatWindow
        session={chat.activeSession}
        userName={user.username}
        loading={chat.loading || attaching}
        error={chat.error}
        onDismissError={chat.dismissError}
        onSend={handleSend}
        allowFile={allowFileAttach}
        contextFile={contextFile}
        contextFiles={accessibleFiles}
        onPickContext={(id) => chat.attachContextFile(id || undefined)}
        onClearContext={() => chat.attachContextFile(undefined)}
      />
    </div>
  )
}
