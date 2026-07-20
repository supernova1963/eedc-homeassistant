/**
 * HilfeV4 — Hilfe-Sicht der IA-V4 (R2b, 2026-07-20).
 *
 * Ersetzt den `V4Platzhalter` unter `/v4/hilfe`. Fläche auf demselben statischen
 * `help/`-System wie die V3-Seite (`pages/Hilfe.tsx`) — die Daten-/Link-Logik
 * teilen sich beide über den Hook {@link useHelpKatalog} (EINE Code-Wahrheit,
 * keine zweite Fetch-/Rewrite-Kopie). Inhalt rendert die geteilte
 * {@link MarkdownDoc}-SoT.
 *
 * Layout = V4-Schale ({@link ViewShell}) mit TOC-Sidebar + Content: Kategorie-TOC
 * (Einstieg/Handbuch/Referenz in Index-Reihenfolge) links, Markdown rechts;
 * mobil klappt die TOC in einen SoT-`Select`. „Was ist neu" bekommt einen
 * eigenen, prominenten Einstieg oben (bisher nur ein Slug unter „Einstieg").
 *
 * `?doc=<slug>`+`#hash`-Deep-Links bleiben kompatibel (Bestands-/Foren-Links):
 * die Sub-Navigation setzt denselben `?doc=`-Parameter, Querverweise laufen über
 * den geteilten Link-Rewriter mit `/v4/hilfe`-Basispfad.
 */
import { useCallback, useMemo, useRef } from 'react'
import { Link, useNavigate, useSearchParams, useLocation } from 'react-router-dom'
import { BookOpen, Sparkles, ExternalLink } from 'lucide-react'
import MarkdownDoc from '../components/ui/MarkdownDoc'
import { Select } from '../components/ui'
import type { SelectItem } from '../components/ui/Select'
import { ViewShell } from './ViewShell'
import {
  useHelpKatalog,
  makeHelpLinkComponent,
  scrollToHashInArticle,
  DEFAULT_SLUG,
} from '../hooks/useHelpKatalog'

/** „Was ist neu" — eigener Einstieg oben, daher aus der Kategorie-Liste gelöst. */
const NEU_SLUG = 'was-ist-neu'

export default function HilfeV4() {
  const [searchParams] = useSearchParams()
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

  const linkComponent = useMemo(
    () => makeHelpLinkComponent({ rewriteLink, navigate, basePath: '/v4/hilfe', scrollToHash }),
    [rewriteLink, navigate, scrollToHash],
  )

  // „Was ist neu" liegt als prominenter Einstieg oben → aus der Desktop-TOC
  // herauslösen (kein Doppel-Eintrag). Der Mobile-Select behält alle Einträge,
  // damit sein `value` immer eine gültige Option trifft.
  const neuDoc = useMemo(
    () => grouped.flatMap((g) => g.items).find((d) => d.slug === NEU_SLUG),
    [grouped],
  )
  const kategorien = useMemo(
    () =>
      grouped
        .map((g) => ({ category: g.category, items: g.items.filter((d) => d.slug !== NEU_SLUG) }))
        .filter((g) => g.items.length > 0),
    [grouped],
  )
  const selectItems: SelectItem[] = useMemo(
    () =>
      grouped.map((g) => ({
        label: g.category,
        options: g.items.map((d) => ({ value: d.slug, label: d.title })),
      })),
    [grouped],
  )

  const tocLinkCls = (slug: string) =>
    `block w-full text-left px-2 py-1.5 rounded text-sm transition-colors ${
      slug === activeSlug
        ? 'bg-primary-50 text-primary-700 font-medium dark:bg-primary-900/30 dark:text-primary-300'
        : 'text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'
    }`

  return (
    <ViewShell>
      <div className="lg:h-full lg:flex lg:flex-row lg:min-h-0">
        {/* Sidebar / TOC — A9-Ausnahme (check:scrollschatten-Allowlist): eigener
            Sicht-Scroller ab lg mit nativem Balken, wie die ViewShell-Hülle. */}
        <aside className="lg:w-72 lg:flex-shrink-0 lg:overflow-y-auto lg:border-r border-gray-200 dark:border-gray-700 p-3 sm:p-4">
          {/* „Was ist neu" — eigener, prominenter Einstieg (Desktop + Mobile) */}
          {neuDoc && (
            <Link
              to={`/v4/hilfe?doc=${NEU_SLUG}`}
              className={`flex items-center gap-2 px-3 py-2.5 mb-3 rounded-lg border text-sm font-medium transition-colors ${
                activeSlug === NEU_SLUG
                  ? 'bg-primary-600 text-white border-primary-600'
                  : 'bg-primary-50 text-primary-700 border-primary-200 hover:bg-primary-100 dark:bg-primary-900/30 dark:text-primary-300 dark:border-primary-800 dark:hover:bg-primary-900/50'
              }`}
            >
              <Sparkles className="w-4 h-4 flex-shrink-0" />
              {neuDoc.title}
            </Link>
          )}

          {/* Mobile-Dropdown (SoT-Select) */}
          <div className="lg:hidden mb-2">
            <label htmlFor="hilfe-v4-doc-select" className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
              Dokument
            </label>
            <Select
              id="hilfe-v4-doc-select"
              value={activeSlug}
              onChange={(e) => navigate(`/v4/hilfe?doc=${e.target.value}`)}
              aria-label="Hilfe-Dokument wählen"
              options={selectItems}
            />
          </div>

          {/* Desktop-TOC */}
          <nav aria-label="Hilfe-Navigation" className="hidden lg:block">
            <div className="flex items-center gap-2 px-2 pb-2 mb-1 border-b border-gray-200 dark:border-gray-700">
              <BookOpen className="w-4 h-4 text-primary-600 dark:text-primary-400" />
              <h2 className="text-sm font-semibold text-gray-900 dark:text-white">Hilfe</h2>
            </div>
            {kategorien.map((g) => (
              <div key={g.category} className="mt-2">
                <p className="px-2 pb-1 text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider">
                  {g.category}
                </p>
                <ul className="space-y-0.5">
                  {g.items.map((d) => (
                    <li key={d.slug}>
                      <Link to={`/v4/hilfe?doc=${d.slug}`} className={tocLinkCls(d.slug)}>
                        {d.title}
                      </Link>
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
        {/* Eigener Inhalts-Scroller ab lg (die ViewShell-Hülle bleibt dann leer-
            scrollend); der Sprung-an-den-Anfang bei Doc-Wechsel läuft über
            onDocLoaded, das Anker-Scrollen über scrollToHash. A9-Ausnahme
            (check:scrollschatten-Allowlist): Sicht-Scroller mit nativem Balken. */}
        <article
          ref={contentRef}
          className="flex-1 min-w-0 lg:overflow-y-auto p-4 sm:p-6"
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
    </ViewShell>
  )
}
