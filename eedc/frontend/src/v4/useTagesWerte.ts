/**
 * useTagesWerte — lädt Tages-Energieprofile für einen Zeitraum (von..bis) und
 * optional denselben Zeitraum im Vorjahr (für den Werte-Werkbank-Vergleich).
 * Quelle: `energieProfilApi.getTageWerte` (ADR-001-konform, kein Frontend-Compute).
 */
import { energieProfilApi, type TagWerte } from '../api/energie_profil'
import { useApiData } from '../hooks/useApiData'

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
  // R18-2 (SWR + keepPreviousData): Zeitraum-Wechsel aktualisiert in-place statt
  // Skeleton; beim Sub-Tab-Wechsel steht der letzte Stand sofort (Sicht-Cache).
  const q = useApiData<{ rows: TagWerte[]; vorjahrRows: TagWerte[] | null }>(
    async () => {
      const vergleich = vergleichVon && vergleichBis
        ? energieProfilApi.getTageWerte(anlageId!, vergleichVon, vergleichBis).catch(() => [] as TagWerte[])
        : Promise.resolve(null)
      const [r, v] = await Promise.all([energieProfilApi.getTageWerte(anlageId!, von, bis), vergleich])
      return { rows: r, vorjahrRows: v }
    },
    [anlageId, von, bis, vergleichVon, vergleichBis],
    {
      enabled: !!(anlageId && von && bis),
      swrKey: `v4-tageswerte:${anlageId}:${von}:${bis}:${vergleichVon}:${vergleichBis}`,
      keepPreviousData: true,
    },
  )
  return {
    rows: q.data?.rows ?? [],
    vorjahrRows: q.data?.vorjahrRows ?? null,
    loading: q.loading,
    error: q.data == null ? q.error : null,
  }
}
