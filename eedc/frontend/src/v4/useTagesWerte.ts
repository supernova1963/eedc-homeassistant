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
  /** Wärmepumpen-Tagesreihe mitladen (29.10.2026) — nur, wenn eine dieser Spalten eingeblendet ist; gilt für beide
   *  Abfragen (Zeitraum und Vergleich). */
  mitWaerme = false,
): TagesWerteResult {
  // R18-2 (SWR + keepPreviousData): Zeitraum-Wechsel aktualisiert in-place statt
  // Skeleton; beim Sub-Tab-Wechsel steht der letzte Stand sofort (Sicht-Cache).
  // ⚠ Mit `mitWaerme` KEIN In-Place (Entscheid Gernot 28.10.2026): die Abfrage dauert über lange Zeiträume Sekunden,
  // und die Tabelle soll in der Zeit weder den alten noch einen halben Stand zeigen — `loading` bleibt bis alles da
  // ist, der Block zeigt die Lade-Anzeige. Ein Cache-Stand derselben Abfrage steht weiterhin sofort (er ist vollständig).
  const q = useApiData<{ rows: TagWerte[]; vorjahrRows: TagWerte[] | null }>(
    async () => {
      const vergleich = vergleichVon && vergleichBis
        ? energieProfilApi.getTageWerte(anlageId!, vergleichVon, vergleichBis, mitWaerme).catch(() => [] as TagWerte[])
        : Promise.resolve(null)
      const [r, v] = await Promise.all([energieProfilApi.getTageWerte(anlageId!, von, bis, mitWaerme), vergleich])
      return { rows: r, vorjahrRows: v }
    },
    [anlageId, von, bis, vergleichVon, vergleichBis, mitWaerme],
    {
      enabled: !!(anlageId && von && bis),
      swrKey: `v4-tageswerte:${anlageId}:${von}:${bis}:${vergleichVon}:${vergleichBis}${mitWaerme ? ':waerme' : ''}`,
      keepPreviousData: !mitWaerme,
    },
  )
  return {
    rows: q.data?.rows ?? [],
    vorjahrRows: q.data?.vorjahrRows ?? null,
    loading: q.loading,
    error: q.data == null ? q.error : null,
  }
}
