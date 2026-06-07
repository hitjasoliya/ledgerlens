import { useState } from 'react'
import { UploadIcon } from '../ui/Icon'
import { previewLayout, API_BASE } from '../../lib/api'
import './LayoutInspector.css'

interface Region {
  type: string
  bbox: [number, number, number, number]
  score: number
  page: number
}

interface PageData {
  page_num: number
  image_url: string
  width: number
  height: number
  regions: Region[]
}

const REGION_COLORS: Record<string, string> = {
  title: 'rgba(168, 85, 247, 0.4)', // purple
  text: 'rgba(34, 197, 94, 0.4)',  // green
  list: 'rgba(234, 179, 8, 0.4)',  // yellow
  table: 'rgba(59, 130, 246, 0.4)', // blue
  figure: 'rgba(249, 115, 22, 0.4)' // orange
}

const REGION_BORDER: Record<string, string> = {
  title: 'rgb(168, 85, 247)',
  text: 'rgb(34, 197, 94)',
  list: 'rgb(234, 179, 8)',
  table: 'rgb(59, 130, 246)',
  figure: 'rgb(249, 115, 22)'
}

export function LayoutInspector() {
  const [loading, setLoading] = useState(false)
  const [pages, setPages] = useState<PageData[]>([])
  const [error, setError] = useState<string | null>(null)

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    setLoading(true)
    setError(null)
    setPages([])

    try {
      const data = await previewLayout(file)
      setPages(data.pages)
    } catch (err: any) {
      setError(err.message || 'Failed to analyze layout')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="layout-inspector">
      <div className="layout-inspector__container">
        <div className="layout-inspector__header">
          <h2>Layout Inspector</h2>
          <p>Upload a PDF to see how the backend layout detector sees the document.</p>
        </div>

        <div className="layout-inspector__upload-card">
          <label className="layout-inspector__upload-area" disabled={loading}>
            <div className="layout-inspector__upload-content">
              <UploadIcon size={24} className="layout-inspector__upload-icon" />
              <p className="layout-inspector__upload-text">
                <span>Click to upload</span>
              </p>
              <p className="layout-inspector__upload-hint">PDF documents only</p>
            </div>
            <input 
              type="file" 
              className="layout-inspector__hidden-input" 
              accept="application/pdf"
              onChange={handleFileUpload}
              disabled={loading}
            />
          </label>
        </div>

        {error && (
          <div className="layout-inspector__error">
            {error}
          </div>
        )}

        {loading && (
          <div className="layout-inspector__loading">
            <div className="layout-inspector__spinner"></div>
            <span className="layout-inspector__loading-text">Analyzing PDF layout (this may take a while)...</span>
          </div>
        )}

        {!loading && pages.length > 0 && (
          <div className="layout-inspector__results">
            {pages.map((page, idx) => (
              <div key={idx} className="layout-inspector__page">
                <div className="layout-inspector__page-header">
                  <span>Page {page.page_num}</span>
                  <span className="layout-inspector__page-meta">{page.regions.length} regions detected</span>
                </div>
                <div className="layout-inspector__page-content">
                  <div 
                    className="layout-inspector__canvas"
                    style={{ 
                      maxWidth: `${page.width}px`
                    }}
                  >
                    <img 
                      src={`${API_BASE}${page.image_url}`} 
                      alt={`Page ${page.page_num}`}
                      className="layout-inspector__image"
                    />
                    
                    {page.regions.map((region, rIdx) => {
                      const [x1, y1, x2, y2] = region.bbox
                      const type = region.type.toLowerCase()
                      
                      const left = (x1 / page.width) * 100
                      const top = (y1 / page.height) * 100
                      const width = ((x2 - x1) / page.width) * 100
                      const height = ((y2 - y1) / page.height) * 100

                      return (
                        <div
                          key={rIdx}
                          className="layout-inspector__region"
                          style={{
                            left: `${left}%`,
                            top: `${top}%`,
                            width: `${width}%`,
                            height: `${height}%`,
                            backgroundColor: REGION_COLORS[type] || 'rgba(156, 163, 175, 0.4)',
                            border: `2px solid ${REGION_BORDER[type] || 'rgb(156, 163, 175)'}`,
                          }}
                        >
                          <div className="layout-inspector__region-tooltip">
                            {region.type} ({(region.score * 100).toFixed(1)}%)
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
