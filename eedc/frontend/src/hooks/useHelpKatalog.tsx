/**
 * useHelpKatalog — geteilte Daten-/Link-Logik der In-App-Hilfe (R2b, 2026-07-20).
 *
 * EINE Code-Wahrheit (Regel 0/Konvergenz): der Index-/Dokument-Fetch, die
 * Kategorie-Gruppierung, der `?doc=<slug>`+`#hash`-Deep-Link-Rewrite und das
 * Anker-Scrollen lebten bisher NUR in `pages/Hilfe.tsx`. Für die V4-Sicht
 * (`v4/HilfeV4.tsx`) wäre eine zweite Kopie Drift-Gefahr → hier extrahiert,
 * von V3-Hilfe UND HilfeV4 genutzt.
 *
 * Der EINZIGE Unterschied der beiden Aufrufer ist der Router-Basispfad
 * (`/hilfe` vs. `/v4/hilfe`) beim Klick auf einen internen Querverweis — dafür
 * nimmt {@link makeHelpLinkComponent} `basePath` als Parameter. `rewriteLink`
 * bindet Querverweise an **Dateinamen** (index.json → slug) — die help/-Dateien
 * dürfen daher NICHT umbenannt werden (Bestands-/Foren-Links).
 */
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { NavigateFunction } from 'react-router-dom'

export interface HelpDoc {
  slug: string
  title: string
  category: string
  filename: string
}

export const HELP_BASE = 'help/' // relativ — Vite base ist './'
export const DEFAULT_SLUG = 'benutzerhandbuch'

/** Ergebnis des Link-Rewrites: intern (`?doc=`), Anker (`#`) oder extern. */
export type LinkRewrite =
  | { type: 'internal'; target: string }
  | { type: 'anchor'; target: string }
  | { type: 'external'; target: string }

export interface HelpKatalog {
  docs: HelpDoc[] | null
  /** Kategorien in Index-Reihenfolge, je Kategorie ihre Dokumente. */
  grouped: { category: string; items: HelpDoc[] }[]
  activeDoc: HelpDoc | undefined
  content: string
  loading: boolean
  error: string | null
  rewriteLink: (href: string | undefined) => LinkRewrite
}

/**
 * Zu einem Anker im Hilfe-Artikel scrollen. Der tatsächlich scrollbare Vorfahr
 * wird gesucht (verschachtelte overflow-Container: main > article — je nach
 * Höhen-Constraint scrollt mal das eine, mal das andere).
 */
export function scrollToHashInArticle(article: HTMLElement | null, hash: string): void {
  if (!hash || !article) return
  const decoded = (() => { try { return decodeURIComponent(hash) } catch { return hash } })()
  let el: HTMLElement | null = article.ownerDocument.getElementById(decoded)
  if (!el) {
    const escaped = decoded.replace(/"/g, '\\"')
    el = article.querySelector<HTMLElement>(`a[name="${escaped}"]`)
  }
  if (!el || !article.contains(el)) return
  let container: HTMLElement = article
  let node: HTMLElement | null = article
  while (node) {
    if (node.scrollHeight > node.clientHeight + 1) { container = node; break }
    node = node.parentElement
  }
  const offset = el.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop
  // `scrollTo?.()` — jsdom (Tests) implementiert Element.scrollTo nicht; im Browser vorhanden.
  container.scrollTo?.({ top: Math.max(0, offset - 8), behavior: 'auto' })
}

/**
 * Lädt Index + aktives Dokument und liefert Gruppierung + Link-Rewriter.
 *
 * `onDocLoaded(targetHash)` wird nach jedem erfolgreichen Dokument-Fetch in
 * `requestAnimationFrame` aufgerufen — der Aufrufer scrollt darin zum Hash bzw.
 * an den Anfang (DOM-/Ref-Sache, bleibt beim Host). Effekt-Deps identisch zur
 * ursprünglichen `Hilfe.tsx`-Fassung (Verhaltens-Parität für V3).
 */
export function useHelpKatalog(
  activeSlug: string,
  targetHash: string,
  onDocLoaded?: (targetHash: string) => void,
): HelpKatalog {
  const [docs, setDocs] = useState<HelpDoc[] | null>(null)
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Callback über Ref → der Dokument-Effekt hängt NICHT an seiner Identität
  // (sonst re-fetch bei jedem Render); Verhalten bleibt frisch.
  const onLoadedRef = useRef(onDocLoaded)
  onLoadedRef.current = onDocLoaded

  // Index laden
  useEffect(() => {
    fetch(`${HELP_BASE}index.json`)
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
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
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.text() })
      .then((md) => {
        setContent(md)
        // Nach Dokumentenwechsel: zu Hash scrollen oder an den Anfang.
        requestAnimationFrame(() => onLoadedRef.current?.(targetHash))
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

  // Kategorien für Sidebar gruppieren (Reihenfolge wie im Index)
  const grouped = useMemo(() => {
    if (!docs) return []
    const order: string[] = []
    const byCat = new Map<string, HelpDoc[]>()
    docs.forEach((d) => {
      if (!byCat.has(d.category)) { order.push(d.category); byCat.set(d.category, []) }
      byCat.get(d.category)!.push(d)
    })
    return order.map((cat) => ({ category: cat, items: byCat.get(cat)! }))
  }, [docs])

  const rewriteLink = useMemo(() => {
    return (href: string | undefined): LinkRewrite => {
      if (!href) return { type: 'external', target: '#' }
      if (href.startsWith('#')) return { type: 'anchor', target: href }
      // Absolute URLs (http/https/mailto/…) immer extern
      if (/^[a-z][a-z0-9+.-]*:/i.test(href)) return { type: 'external', target: href }
      // Relative .md-Links: bekannt → intern, unbekannt → GitHub-URL der Doku
      const mdMatch = href.match(/^([^#?]+\.md)(#.*)?$/)
      if (mdMatch) {
        const [, file, hash] = mdMatch
        const slug = filenameToSlug.get(file)
        if (slug) return { type: 'internal', target: `?doc=${slug}${hash || ''}` }
        return {
          type: 'external',
          target: `https://github.com/supernova1963/eedc-homeassistant/blob/main/docs/${file}${hash || ''}`,
        }
      }
      return { type: 'external', target: href }
    }
  }, [filenameToSlug])

  const activeDoc = docs?.find((d) => d.slug === activeSlug)

  return { docs, grouped, activeDoc, content, loading, error, rewriteLink }
}

/**
 * Baut die `linkComponent` für {@link MarkdownDoc}: interne `?doc=`-Links
 * navigieren im gegebenen `basePath` (`/hilfe` bzw. `/v4/hilfe`), Anker scrollen
 * im Artikel, externe fallen auf den MarkdownDoc-Default (neuer Tab). EINE
 * Implementierung für beide Sichten — der Basispfad ist der einzige Unterschied.
 */
export function makeHelpLinkComponent(opts: {
  rewriteLink: (href: string | undefined) => LinkRewrite
  navigate: NavigateFunction
  basePath: string
  scrollToHash: (hash: string) => void
}): (href: string | undefined, children: ReactNode, name?: string) => ReactNode | null {
  const { rewriteLink, navigate, basePath, scrollToHash } = opts
  return (href, children, name) => {
    if (!href && name) return <a id={name} />
    if (!href) return null
    const { type, target } = rewriteLink(href)
    if (type === 'internal') {
      return (
        <a
          href={target}
          onClick={(e) => {
            e.preventDefault()
            const [params, hash] = target.replace(/^\?/, '').split('#')
            navigate(`${basePath}?${params}${hash ? '#' + hash : ''}`)
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
          onClick={(e) => { e.preventDefault(); scrollToHash(target.slice(1)) }}
          className="text-primary-600 dark:text-primary-400 hover:underline"
        >
          {children}
        </a>
      )
    }
    return null // extern → MarkdownDoc-Default (neuer Tab + Icon)
  }
}
