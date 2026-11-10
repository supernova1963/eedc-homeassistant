/**
 * LoesungswegPanel — der Lösungsweg eines Befunds neben der Liste (Etappe E3, Konzept §3.5, Entscheid §11 Nr. 10).
 *
 * Zeigt das Handbuch «Daten-Checker» (`/hilfe?doc=daten-checker`) über die geteilte Hilfe-Mechanik
 * (`useHelpKatalog` + `MarkdownDoc`) und springt zum Abschnitt des Befunds (`loesungswegAnker`: bis E5 der Abschnitt der
 * Kategorie). Der Befund bleibt sichtbar: als seitlicher Einschub neben der Liste (`als="einschub"`), auf dem Handy und
 * im Komponenten-Hub als Dialog (`als="dialog"`).
 *
 * «In eigenem Fenster öffnen» nur **außerhalb** von Home Assistant: in der Companion-App bzw. hinter dem Ingress öffnet
 * ein `_blank`-Fenster extern ohne Ingress-Sitzung (401, `lib/download.ts`); dort steht stattdessen der Hinweis.
 */
import { useCallback, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { ExternalLink, X } from 'lucide-react'
import { Button, Card, Modal } from '../ui'
import MarkdownDoc from '../ui/MarkdownDoc'
import type { CheckErgebnis } from '../../api/datenChecker'
import { KATEGORIE_LABELS, loesungswegAnker } from '../../config/datenCheckerKategorien'
import { makeHelpLinkComponent, scrollToHashInArticle, useHelpKatalog } from '../../hooks/useHelpKatalog'
import { istImHaRahmen } from '../../lib/download'

export const LOESUNGSWEG_DOC = 'daten-checker'

export default function LoesungswegPanel({ befund, als, onClose }: {
  befund: CheckErgebnis
  als: 'einschub' | 'dialog'
  onClose: () => void
}) {
  const navigate = useNavigate()
  const ref = useRef<HTMLDivElement>(null)
  const anker = loesungswegAnker(befund.kategorie, befund.code)
  const scrollToHash = useCallback((hash: string) => scrollToHashInArticle(ref.current, hash.replace(/^#/, '')), [])
  const { content, loading, error, rewriteLink } = useHelpKatalog(LOESUNGSWEG_DOC, anker, scrollToHash)
  const linkComponent = useMemo(
    () => makeHelpLinkComponent({ rewriteLink, navigate, basePath: '/hilfe', scrollToHash }),
    [rewriteLink, navigate, scrollToHash],
  )
  const imHaRahmen = istImHaRahmen()
  const titel = `Lösungsweg: ${KATEGORIE_LABELS[befund.kategorie] ?? befund.kategorie}`

  const inhalt = (
    <div className="space-y-3">
      <p className="text-sm text-gray-700 dark:text-gray-300">{befund.meldung}</p>
      <div className="flex flex-wrap items-center gap-2">
        {imHaRahmen ? (
          <span className="text-xs text-gray-500 dark:text-gray-400" data-testid="loesungsweg-hinweis">
            Im Panel öffnen — in der Home-Assistant-App öffnet ein eigenes Fenster ohne Anmeldung.
          </span>
        ) : (
          <Button variant="secondary" size="sm"
            onClick={() => window.open(`#/hilfe?doc=${LOESUNGSWEG_DOC}#${anker}`, '_blank', 'noopener')}>
            <ExternalLink className="h-3 w-3 mr-1" />
            In eigenem Fenster öffnen
          </Button>
        )}
      </div>
      <div ref={ref} className="markdown-help max-h-[70vh] overflow-y-auto text-gray-800 dark:text-gray-200"
        data-testid="loesungsweg-inhalt">
        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        {loading && !content && <p className="text-sm text-gray-500 dark:text-gray-400">Lade …</p>}
        {content && <MarkdownDoc markdown={content} linkComponent={linkComponent} />}
      </div>
    </div>
  )

  if (als === 'dialog') {
    return <Modal isOpen onClose={onClose} title={titel} size="xl">{inhalt}</Modal>
  }
  return (
    <Card>
      <div className="p-4 space-y-2" data-testid="loesungsweg-panel">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{titel}</h3>
          <Button variant="ghost" size="sm" onClick={onClose} title="Schließen" aria-label="Lösungsweg schließen">
            <X className="h-4 w-4" />
          </Button>
        </div>
        {inhalt}
      </div>
    </Card>
  )
}
