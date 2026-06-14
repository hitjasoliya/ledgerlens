import type { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import './MarkdownRenderer.css'

type Props = {
  content: string
}

export function MarkdownRenderer({ content }: Props) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        table: ({ children }) => (
          <div className="md-table-wrap">
            <table className="md-table">{children}</table>
          </div>
        ),
        thead: ({ children }) => <thead>{children}</thead>,
        th: ({ children }) => <th>{children}</th>,
        td: ({ children }) => <TdRenderer>{children}</TdRenderer>,
        tr: ({ children }) => <tr>{children}</tr>,
        strong: ({ children }) => <strong className="md-strong">{children}</strong>,
        em: ({ children }) => <em className="md-em">{children}</em>,
        code: (props) => {
          const { className, children } = props
          const isInline = !className
          if (isInline) {
            return <code className="md-code-inline">{children}</code>
          }
          return <code className="md-code-block">{children}</code>
        },
        pre: ({ children }) => <pre className="md-pre">{children}</pre>,
        ul: ({ children }) => <ul className="md-list">{children}</ul>,
        ol: ({ children }) => <ol className="md-list">{children}</ol>,
        li: ({ children }) => <li className="md-li">{children}</li>,
        p: ({ children }) => <p className="md-p">{children}</p>,
        a: ({ href, children }) => (
          <a className="md-link" href={href} target="_blank" rel="noopener noreferrer">
            {children}
          </a>
        ),
        blockquote: ({ children }) => (
          <blockquote className="md-blockquote">{children}</blockquote>
        ),
        h1: ({ children }) => <h1 className="md-h1">{children}</h1>,
        h2: ({ children }) => <h2 className="md-h2">{children}</h2>,
        h3: ({ children }) => <h3 className="md-h3">{children}</h3>,
        hr: () => <hr className="md-hr" />,
      }}
    >
      {content}
    </ReactMarkdown>
  )
}

function TdRenderer({ children }: { children: ReactNode }) {
  const text = extractText(children)
  if (text && isNumeric(text)) {
    return <td className="md-td md-td--number">{children}</td>
  }
  if (text && isNegativePercent(text)) {
    return <td className="md-td md-td--negative">{children}</td>
  }
  if (text && isPositivePercent(text)) {
    return <td className="md-td md-td--positive">{children}</td>
  }
  return <td className="md-td">{children}</td>
}

function extractText(node: ReactNode): string {
  if (typeof node === 'string') return node
  if (typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(extractText).join('')
  if (node && typeof node === 'object' && 'props' in node) {
    return extractText((node as { props: { children?: ReactNode } }).props.children)
  }
  return ''
}

function isNumeric(text: string): boolean {
  return /^[\s$€£¥%()\-]*[\d,.]+[\s$€£¥%()\-]*$/.test(text.trim())
}

function isNegativePercent(text: string): boolean {
  return /\(\d+[.%]/.test(text) || /-\d+[.%]/.test(text) || text.includes('(%)')
}

function isPositivePercent(text: string): boolean {
  return /^\s*\+?\d+[.%]/.test(text.trim()) || /\d+%\s*(increase|growth|up)/i.test(text.trim())
}
