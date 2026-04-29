/**
 * In-App-Hilfe-Seite (#130, Discussion Safi105).
 *
 * Lädt kuratierte Markdown-Dateien aus public/help/ und rendert sie
 * mit react-markdown. Sidebar listet alle Dokumente, URL-Parameter
 * `?doc=<slug>` macht Direktlinks teilbar.
 *
 * Sync-Quelle: docs/ — siehe scripts/sync-help.sh
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams, useNavigate, useLocation } from 'react-router-dom'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSlug from 'rehype-slug'
import rehypeRaw from 'rehype-raw'
import { BookOpen, ChevronDown, ExternalLink } from 'lucide-react'

interface HelpDoc {
  slug: string
  title: string
  category: string
  filename: string
}

const HELP_BASE = 'help/'  // relativ — Vite base ist './'
const DEFAULT_SLUG = 'benutzerhandbuch'

export default function Hilfe() {
  const [docs, setDocs] = useState<HelpDoc[] | null>(null)
  const [content, setContent] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const location = useLocation()
  const contentRef = useRef<HTMLDivElement>(null)

  const activeSlug = searchParams.get('doc') || DEFAULT_SLUG
  const targetHash = location.hash ? location.hash.slice(1) : ''

  const scrollToHash = (hash: string) => {
    const article = contentRef.current
    if (!hash || !article) return
    const decoded = (() => { try { return decodeURIComponent(hash) } catch { return hash } })()
    let el: HTMLElement | null = article.ownerDocument.getElementById(decoded)
    if (!el) {
      const escaped = decoded.replace(/"/g, '\\"')
      el = article.querySelector<HTMLElement>(`a[name="${escaped}"]`)
    }
    if (!el || !article.contains(el)) return
    // Tatsächlich scrollbaren Vorfahren finden — Layout hat verschachtelte
    // overflow-Container (main > article); je nach Höhen-Constraint scrollt
    // mal das eine, mal das andere.
    let container: HTMLElement = article
    let node: HTMLElement | null = article
    while (node) {
      if (node.scrollHeight > node.clientHeight + 1) { container = node; break }
      node = node.parentElement
    }
    const offset = el.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop
    container.scrollTo({ top: Math.max(0, offset - 8), behavior: 'auto' })
  }

  // Index laden
  useEffect(() => {
    fetch(`${HELP_BASE}index.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((data: HelpDoc[]) => setDocs(data))
      .catch((e) => setError(`Hilfe-Inhalte konnten nicht geladen werden: ${e.message}`))
  }, [])

  // Aktuelles Dokument laden
  useEffect(() => {
    if (!docs) return
    const doc = docs.find((d) => d.slug === activeSlug)
    if (!doc) {
      setError(`Hilfe-Dokument "${activeSlug}" nicht gefunden.`)
      setContent('')
      return
    }
    setLoading(true)
    setError(null)
    fetch(`${HELP_BASE}${doc.slug}.md`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.text()
      })
      .then((md) => {
        setContent(md)
        // Nach Dokumentenwechsel: zu Hash scrollen oder an den Anfang
        requestAnimationFrame(() => {
          if (targetHash) scrollToHash(targetHash)
          else contentRef.current?.scrollTo({ top: 0, behavior: 'auto' })
        })
      })
      .catch((e) => setError(`Dokument konnte nicht geladen werden: ${e.message}`))
      .finally(() => setLoading(false))
  }, [docs, activeSlug, targetHash])

  // Filename → slug für interne Link-Rewrites
  const filenameToSlug = useMemo(() => {
    const map = new Map<string, string>()
    docs?.forEach((d) => map.set(d.filename, d.slug))
    return map
  }, [docs])

  // Kategorien für Sidebar gruppieren (Reihenfolge wie im index)
  const grouped = useMemo(() => {
    if (!docs) return []
    const order: string[] = []
    const byCat = new Map<string, HelpDoc[]>()
    docs.forEach((d) => {
      if (!byCat.has(d.category)) {
        order.push(d.category)
        byCat.set(d.category, [])
      }
      byCat.get(d.category)!.push(d)
    })
    return order.map((cat) => ({ category: cat, items: byCat.get(cat)! }))
  }, [docs])

  const selectDoc = (slug: string) => {
    setSearchParams({ doc: slug })
  }

  // Link-Rewriting für Markdown
  const rewriteLink = (href: string | undefined): { type: 'internal' | 'anchor' | 'external'; target: string } => {
    if (!href) return { type: 'external', target: '#' }
    if (href.startsWith('#')) return { type: 'anchor', target: href }
    // Absolute URLs (http/https/mailto/…) immer extern
    if (/^[a-z][a-z0-9+.-]*:/i.test(href)) return { type: 'external', target: href }
    // Relative .md-Links: bekannt → intern, unbekannt → GitHub-URL der Doku
    const mdMatch = href.match(/^([^#?]+\.md)(#.*)?$/)
    if (mdMatch) {
      const [, file, hash] = mdMatch
      const slug = filenameToSlug.get(file)
      if (slug) {
        return { type: 'internal', target: `?doc=${slug}${hash || ''}` }
      }
      return {
        type: 'external',
        target: `https://github.com/supernova1963/eedc-homeassistant/blob/main/docs/${file}${hash || ''}`,
      }
    }
    return { type: 'external', target: href }
  }

  const activeDoc = docs?.find((d) => d.slug === activeSlug)

  return (
    <div className="flex flex-col lg:flex-row gap-4 h-full">
      {/* Sidebar Desktop / Dropdown Mobile */}
      <aside className="lg:w-72 lg:flex-shrink-0">
        {/* Mobile-Dropdown */}
        <div className="lg:hidden mb-2">
          <label htmlFor="hilfe-doc-select" className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
            Dokument
          </label>
          <div className="relative">
            <select
              id="hilfe-doc-select"
              value={activeSlug}
              onChange={(e) => selectDoc(e.target.value)}
              className="w-full appearance-none px-3 py-2 pr-8 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              {grouped.map((g) => (
                <optgroup key={g.category} label={g.category}>
                  {g.items.map((d) => (
                    <option key={d.slug} value={d.slug}>
                      {d.title}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
          </div>
        </div>

        {/* Desktop-Sidebar */}
        <nav
          aria-label="Hilfe-Navigation"
          className="hidden lg:block bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-3 sticky top-0"
        >
          <div className="flex items-center gap-2 px-2 pb-2 mb-1 border-b border-gray-200 dark:border-gray-700">
            <BookOpen className="w-4 h-4 text-primary-600 dark:text-primary-400" />
            <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Hilfe</h2>
          </div>
          {grouped.map((g) => (
            <div key={g.category} className="mt-2">
              <p className="px-2 pb-1 text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider">
                {g.category}
              </p>
              <ul className="space-y-0.5">
                {g.items.map((d) => (
                  <li key={d.slug}>
                    <button
                      type="button"
                      onClick={() => selectDoc(d.slug)}
                      className={`w-full text-left px-2 py-1.5 rounded text-sm transition-colors ${
                        d.slug === activeSlug
                          ? 'bg-primary-50 text-primary-700 font-medium dark:bg-primary-900/30 dark:text-primary-300'
                          : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
                      }`}
                    >
                      {d.title}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          <p className="mt-3 pt-2 px-2 border-t border-gray-200 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400">
            Diese Inhalte sind eine Auswahl aus der{' '}
            <a
              href="https://supernova1963.github.io/eedc-homeassistant/"
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary-600 dark:text-primary-400 hover:underline inline-flex items-center gap-0.5"
            >
              Online-Doku <ExternalLink className="w-3 h-3" />
            </a>
            .
          </p>
        </nav>
      </aside>

      {/* Inhalt */}
      <article
        ref={contentRef}
        className="flex-1 min-w-0 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4 sm:p-6 overflow-auto"
      >
        {error && (
          <div className="text-sm text-red-700 bg-red-50 dark:bg-red-900/20 dark:text-red-300 border border-red-200 dark:border-red-800 rounded p-3">
            {error}
          </div>
        )}

        {loading && !error && (
          <p className="text-sm text-gray-500 dark:text-gray-400">Lade …</p>
        )}

        {!loading && !error && content && (
          <div className="markdown-help text-gray-800 dark:text-gray-200">
            {activeDoc && (
              <p className="text-xs text-gray-400 dark:text-gray-500 mb-2">{activeDoc.category}</p>
            )}
            <Markdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeRaw, rehypeSlug]}
              components={{
                h1: ({ children, id }) => (
                  <h1 id={id} className="text-2xl font-bold text-gray-900 dark:text-white mt-2 mb-4 pb-2 border-b border-gray-200 dark:border-gray-700">
                    {children}
                  </h1>
                ),
                h2: ({ children, id }) => (
                  <h2 id={id} className="text-xl font-bold text-gray-900 dark:text-white mt-8 mb-3">{children}</h2>
                ),
                h3: ({ children, id }) => (
                  <h3 id={id} className="text-lg font-semibold text-gray-900 dark:text-white mt-6 mb-2">{children}</h3>
                ),
                h4: ({ children, id }) => (
                  <h4 id={id} className="text-base font-semibold text-gray-900 dark:text-white mt-4 mb-2">{children}</h4>
                ),
                p: ({ children }) => <p className="my-3 leading-relaxed">{children}</p>,
                ul: ({ children }) => <ul className="list-disc pl-6 my-3 space-y-1 leading-relaxed">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal pl-6 my-3 space-y-1 leading-relaxed">{children}</ol>,
                blockquote: ({ children }) => (
                  <blockquote className="border-l-4 border-primary-500 dark:border-primary-400 pl-4 my-4 text-gray-600 dark:text-gray-400 italic">
                    {children}
                  </blockquote>
                ),
                code: ({ inline, children, ...props }: { inline?: boolean; children?: React.ReactNode } & React.HTMLAttributes<HTMLElement>) =>
                  inline ? (
                    <code className="px-1 py-0.5 bg-gray-100 dark:bg-gray-700 text-sm rounded font-mono text-primary-700 dark:text-primary-300" {...props}>
                      {children}
                    </code>
                  ) : (
                    <code className="block" {...props}>
                      {children}
                    </code>
                  ),
                pre: ({ children }) => (
                  <pre className="my-4 p-3 bg-gray-100 dark:bg-gray-900 rounded overflow-x-auto text-sm font-mono text-gray-800 dark:text-gray-200">
                    {children}
                  </pre>
                ),
                table: ({ children }) => (
                  <div className="my-4 overflow-x-auto">
                    <table className="min-w-full text-sm border-collapse">{children}</table>
                  </div>
                ),
                thead: ({ children }) => (
                  <thead className="bg-gray-50 dark:bg-gray-700/50">{children}</thead>
                ),
                th: ({ children }) => (
                  <th className="px-3 py-2 text-left font-semibold text-gray-900 dark:text-white border border-gray-200 dark:border-gray-700">
                    {children}
                  </th>
                ),
                td: ({ children }) => (
                  <td className="px-3 py-2 align-top border border-gray-200 dark:border-gray-700">
                    {children}
                  </td>
                ),
                hr: () => <hr className="my-6 border-gray-200 dark:border-gray-700" />,
                a: ({ href, children, ...rest }) => {
                  const name = (rest as { name?: string }).name
                  // Reine Anker-Targets aus Roh-HTML (z.B. <a name="…"></a>) als ID-Marker rendern
                  if (!href && name) {
                    return <a id={name} />
                  }
                  const { type, target } = rewriteLink(href)
                  if (type === 'internal') {
                    return (
                      <a
                        href={target}
                        onClick={(e) => {
                          e.preventDefault()
                          const [params, hash] = target.replace(/^\?/, '').split('#')
                          navigate(`/hilfe?${params}${hash ? '#' + hash : ''}`)
                        }}
                        className="text-primary-600 dark:text-primary-400 hover:underline"
                      >
                        {children}
                      </a>
                    )
                  }
                  if (type === 'anchor') {
                    return (
                      <a
                        href={target}
                        onClick={(e) => {
                          e.preventDefault()
                          scrollToHash(target.slice(1))
                        }}
                        className="text-primary-600 dark:text-primary-400 hover:underline"
                      >
                        {children}
                      </a>
                    )
                  }
                  return (
                    <a
                      href={target}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-primary-600 dark:text-primary-400 hover:underline inline-flex items-center gap-0.5"
                    >
                      {children}
                      <ExternalLink className="w-3 h-3 inline" />
                    </a>
                  )
                },
              }}
            >
              {content}
            </Markdown>
          </div>
        )}
      </article>
    </div>
  )
}
