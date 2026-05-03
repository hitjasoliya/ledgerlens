import { useCallback, useRef, useState } from 'react'
import type { IngestResponse } from '../types'
import { ingestPdf } from '../api'

export default function IngestPanel() {
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<IngestResponse | null>(null)
  const [dragActive, setDragActive] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFile = (f: File | null) => {
    if (f && !f.name.toLowerCase().endsWith('.pdf')) {
      setError('Only PDF files are supported')
      return
    }
    setFile(f)
    setError(null)
    setResult(null)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragActive(false)
    const f = e.dataTransfer.files[0] ?? null
    handleFile(f)
  }

  const runIngest = useCallback(async () => {
    if (!file) return
    setError(null)
    setResult(null)
    setLoading(true)
    try {
      const data = await ingestPdf(file)
      setResult(data)
      setFile(null)
      if (fileRef.current) fileRef.current.value = ''
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [file])

  return (
    <div className="ingest-panel">
      <div className="ingest-header">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
        </svg>
        <span>Upload PDF</span>
      </div>

      <div
        className={`ingest-dropzone ${dragActive ? 'active' : ''} ${file ? 'has-file' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragActive(true) }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        onClick={() => fileRef.current?.click()}
      >
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf"
          onChange={(e) => handleFile(e.target.files?.[0] ?? null)}
          hidden
        />
        {file ? (
          <div className="ingest-file-info">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
            <span className="ingest-filename">{file.name}</span>
          </div>
        ) : (
          <div className="ingest-placeholder">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            <span>Drop PDF here or click to browse</span>
          </div>
        )}
      </div>

      <button
        type="button"
        className="ingest-btn"
        disabled={!file || loading}
        onClick={() => void runIngest()}
      >
        {loading ? (
          <>
            <span className="ingest-spinner" />
            Uploading...
          </>
        ) : (
          'Upload & Index'
        )}
      </button>

      {error && <div className="ingest-error">{error}</div>}

      {result && (
        <div className="ingest-result">
          <div className="ingest-result-header">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
              <polyline points="22 4 12 14.01 9 11.01" />
            </svg>
            Indexed successfully
          </div>
          <div className="ingest-stats">
            <div className="ingest-stat">
              <span className="ingest-stat-value">{result.pages_parsed}</span>
              <span className="ingest-stat-label">Pages</span>
            </div>
            <div className="ingest-stat">
              <span className="ingest-stat-value">{result.chunks_created}</span>
              <span className="ingest-stat-label">Chunks</span>
            </div>
            <div className="ingest-stat">
              <span className="ingest-stat-value">{result.chunks_indexed}</span>
              <span className="ingest-stat-label">Indexed</span>
            </div>
          </div>
          <div className="ingest-source">{result.source}</div>
        </div>
      )}
    </div>
  )
}
