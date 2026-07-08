import { useState, useEffect, useCallback } from 'react'
import { FileText, ExternalLink } from 'lucide-react'
import { infothekApi } from '../../../api/infothek'
import type { InfothekEintrag } from '../../../types/infothek'
import { useV4Basis } from '../../../hooks'

// Kategorie-Labels für die Infothek-Verknüpfungen (Subset, kein eigener Import nötig)
const KATEGORIE_LABELS: Record<string, string> = {
  garantie: 'Komponente / Datenblatt',
  ansprechpartner: 'Vertragspartner',
  wartungsvertrag: 'Wartungsvertrag',
  marktstammdatenregister: 'MaStR',
  foerderung: 'Förderung',
  versicherung: 'Versicherung',
  stromvertrag: 'Stromvertrag',
  einspeisevertrag: 'Einspeisevertrag',
  steuerdaten: 'Steuerdaten',
  sonstiges: 'Sonstiges',
}

/**
 * Zeigt die mit einer Investition verknüpften Infothek-Einträge (nur im
 * Bearbeiten-Modus). Der Link folgt der Welt (V3/V4) über `useV4Basis` — in
 * der V4-Shell darf nicht auf die V3-Route gesprungen werden (sonst Sackgasse).
 */
export function InfothekVerknuepfungen({ investitionId }: { investitionId: number }) {
  const [eintraege, setEintraege] = useState<InfothekEintrag[]>([])
  const [loading, setLoading] = useState(true)
  const v4Basis = useV4Basis()
  const infothekLink = `#${v4Basis}/einstellungen/infothek`

  const refresh = useCallback(() => {
    setLoading(true)
    infothekApi.listFuerInvestition(investitionId)
      .then(setEintraege)
      .catch(() => setEintraege([]))
      .finally(() => setLoading(false))
  }, [investitionId])

  useEffect(() => { refresh() }, [refresh])

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-900 dark:text-white">Verknüpfte Infothek-Einträge</h3>
        <a
          href={infothekLink}
          className="text-xs text-primary-600 dark:text-primary-400 hover:underline flex items-center gap-1"
        >
          <ExternalLink className="w-3 h-3" />
          Infothek öffnen
        </a>
      </div>

      {loading ? (
        <p className="text-xs text-gray-400 dark:text-gray-500">Laden...</p>
      ) : eintraege.length === 0 ? (
        <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Keine Infothek-Einträge verknüpft. Gerätedaten, Ansprechpartner und Wartungsverträge
            können in der{' '}
            <a href={infothekLink} className="underline text-primary-600 dark:text-primary-400">
              Infothek
            </a>{' '}
            verwaltet und mit dieser Investition verknüpft werden.
          </p>
        </div>
      ) : (
        <div className="space-y-1">
          {eintraege.map(e => (
            <a
              key={e.id}
              href={infothekLink}
              className="flex items-center gap-2 p-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors group"
            >
              <FileText className="w-3.5 h-3.5 text-primary-500 shrink-0" />
              <span className="text-sm text-gray-900 dark:text-white truncate group-hover:underline">
                {e.bezeichnung}
              </span>
              <span className="text-xs text-gray-400 dark:text-gray-500 shrink-0">
                {KATEGORIE_LABELS[e.kategorie] || e.kategorie}
              </span>
            </a>
          ))}
        </div>
      )}
    </div>
  )
}
