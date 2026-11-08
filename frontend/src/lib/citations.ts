import type { Citation } from '../types'

/** One citable place: a document page. Several chunks on the same page share one source. */
export type SourceRef = {
  n: number
  documentId: string
  filename: string
  page: number
}

export type CitationView = {
  /** Answer markdown with tags replaced by numbered `#cite-N` links. */
  markdown: string
  /** Answer text with tags removed, for copying. */
  plain: string
  sources: SourceRef[]
}

const TAG = /\s*\[(?:Citation|Source|Chunk):([^\]]*)\]/gi
const LABEL = /^\s*(?:Citation|Source|Chunk):/i

/**
 * Turns the model's `[Citation: chunk_id, ...]` tags into numbered markers.
 * Numbers follow the order sources first appear in the answer; chunks from the
 * same document page collapse into one number.
 */
export function buildCitationView(content: string, citations: Citation[]): CitationView {
  const byChunk = new Map(citations.map((c) => [c.chunk_id, c]))
  const byPlace = new Map<string, SourceRef>()
  const sources: SourceRef[] = []

  const numberFor = (c: Citation): number => {
    const key = `${c.document_id}#${c.page}`
    let ref = byPlace.get(key)
    if (!ref) {
      ref = { n: sources.length + 1, documentId: c.document_id, filename: c.filename, page: c.page }
      byPlace.set(key, ref)
      sources.push(ref)
    }
    return ref.n
  }

  const markdown = content.replace(TAG, (_match, refs: string) => {
    const numbers: number[] = []
    for (const raw of refs.split(/[,;]/)) {
      const citation = byChunk.get(raw.replace(LABEL, '').trim())
      if (!citation) continue
      const n = numberFor(citation)
      if (!numbers.includes(n)) numbers.push(n)
    }
    return numbers.map((n) => `[${n}](#cite-${n})`).join('')
  })

  // Citations the answer never tagged inline still deserve a source chip.
  for (const c of citations) numberFor(c)

  return { markdown, plain: content.replace(TAG, ''), sources }
}

export function citationNumber(href: string | undefined): number | null {
  const match = href?.match(/^#cite-(\d+)$/)
  return match ? Number(match[1]) : null
}
