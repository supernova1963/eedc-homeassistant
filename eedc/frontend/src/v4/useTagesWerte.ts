/**
 * useTagesWerte — lädt Tages-Energieprofile für einen Zeitraum (von..bis) und
 * optional denselben Zeitraum im Vorjahr (für den Werte-Werkbank-Vergleich).
 * Quelle: `energieProfilApi.getTageWerte` (ADR-001-konform, kein Frontend-Compute).
 */
import { useEffect, useState } from 'react'
import { energieProfilApi, type TagWerte } from '../api/energie_profil'

/** ISO 'YYYY-MM-DD' um ein Jahr zurück (string-sicher, ohne TZ-Drift). */
export function minusEinJahr(iso: string): string {
  const [y, m, d] = iso.split('-')
  return `${Number(y) - 1}-${m}-${d}`
}

export interface TagesWerteResult {
  rows: TagWerte[]
  vorjahrRows: TagWerte[] | null
  loading: boolean
  error: string | null
}

export function useTagesWerte(
  anlageId: number | null | undefined,
  von: string,
  bis: string,
  /** Expliziter Vergleichsbereich (von/bis) oder null = kein Vergleich. */
  vergleichVon: string | null,
  vergleichBis: string | null,
): TagesWerteResult {
  const [rows, setRows] = useState<TagWerte[]>([])
  const [vorjahrRows, setVorjahrRows] = useState<TagWerte[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!anlageId || !von || !bis) { setRows([]); setVorjahrRows(null); setLoading(false); return }
    let aktiv = true
    setLoading(true)
    setError(null)
    const primary = energieProfilApi.getTageWerte(anlageId, von, bis)
    const vergleich = vergleichVon && vergleichBis
      ? energieProfilApi.getTageWerte(anlageId, vergleichVon, vergleichBis).catch(() => [])
      : Promise.resolve(null)
    Promise.all([primary, vergleich])
      .then(([r, v]) => { if (aktiv) { setRows(r); setVorjahrRows(v) } })
      .catch((e) => { if (aktiv) setError(e instanceof Error ? e.message : 'Fehler beim Laden der Tageswerte') })
      .finally(() => { if (aktiv) setLoading(false) })
    return () => { aktiv = false }
  }, [anlageId, von, bis, vergleichVon, vergleichBis])

  return { rows, vorjahrRows, loading, error }
}
