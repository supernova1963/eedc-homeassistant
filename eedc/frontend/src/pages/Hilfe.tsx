/**
 * In-App-Hilfe-Seite (#130, Discussion Safi105).
 *
 * Lädt kuratierte Markdown-Dateien aus public/help/ und rendert sie
 * mit react-markdown. Sidebar listet alle Dokumente, URL-Parameter
 * `?doc=<slug>` macht Direktlinks teilbar.
 *
 * Daten-/Link-Logik liegt seit R2b im geteilten Hook {@link useHelpKatalog}
 * (EINE Code-Wahrheit mit `v4/HilfeV4.tsx`) — hier bleibt nur die V3-Optik.
 *
 * Sync-Quelle: docs/ — siehe scripts/sync-help.sh
 */

import { useCallback, useMemo, useRef } from 'react'
import { useSearchParams, useNavigate, useLocation } from 'react-router-dom'
import { BookOpen, ChevronDown, ExternalLink } from 'lucide-react'
import MarkdownDoc from '../components/ui/MarkdownDoc'
import {
  useHelpKatalog,
  makeHelpLinkComponent,
  scrollToHashInArticle,
  DEFAULT_SLUG,
} from '../hooks/useHelpKatalog'

export default function Hilfe() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const location = useLocation()
  const contentRef = useRef<HTMLDivElement>(null)

  const activeSlug = searchParams.get('doc') || DEFAULT_SLUG
  const targetHash = location.hash ? location.hash.slice(1) : ''

  const scrollToHash = useCallback(
    (hash: string) => scrollToHashInArticle(contentRef.current, hash),
    [],
  )

  const { grouped, activeDoc, content, loading, error, rewriteLink } = useHelpKatalog(
    activeSlug,
    targetHash,
    (hash) => {
      if (hash) scrollToHash(hash)
      else contentRef.current?.scrollTo?.({ top: 0, behavior: 'auto' })
    },
  )

  const selectDoc = (slug: string) => {
    setSearchParams({ doc: slug })
  }

  const linkComponent = useMemo(
    () => makeHelpLinkComponent({ rewriteLink, navigate, basePath: '/hilfe', scrollToHash }),
    [rewriteLink, navigate, scrollToHash],
  )

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
            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 dark:text-gray-500 pointer-events-none" />
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
            <MarkdownDoc markdown={content} linkComponent={linkComponent} />
          </div>
        )}
      </article>
    </div>
  )
}
