/**
 * useAuswertungBasis — gemeinsamer Daten-/Zeitraum-Sockel der monatsdaten-
 * basierten Auswertungen-Sub-Sichten (CO₂, Finanzen, …). Lädt die aggregierten
 * Monatsdaten EINMAL (alle Jahre), hält den Jahr-Filter + abgeleitete Stats +
 * Zeitraum-Label und reicht Strompreis + Tarif-Historie durch — exakt die Props,
 * die die IST-Tabs (`CO2Tab`/`FinanzenTab`) erwarten. Eine Code-Wahrheit: gleicher
 * Lade-/Aggregations-Pfad wie die IST-Seite `Auswertung.tsx` (ADR-001, kein neuer
 * Endpoint), client-seitige Jahr-Filterung (Tab-Wechsel ohne Refetch).
 */
import { useMemo, useState } from 'react'
import { useAggregierteDaten, useAggregierteStats, useAktuellerStrompreis, useStrompreise } from '../hooks'

/** Zeitraum-Label wie IST `getZeitraumLabel` (konkretes Jahr · Einzeljahr · Spanne). */
function zeitraumLabelFuer(jahr: number | 'alle', jahre: number[]): string {
  if (jahr !== 'alle') return `${jahr}`
  if (jahre.length === 0) return 'Alle Jahre'
  if (jahre.length === 1) return `${jahre[0]}`
  return `${Math.min(...jahre)}–${Math.max(...jahre)}`
}

export function useAuswertungBasis(anlageId: number | undefined | null) {
  // S15 (B8): error + refresh mit durchreichen — sonst rendern die Konsumenten bei
  // Fetch-Fehler 0-Wert-KPIs, die wie echte Daten aussehen (stille Leere).
  // R18-2 (SWR): Sicht-Cache — beim Sub-Tab-Wechsel stehen die alten Daten
  // sofort (kein Skeleton), still revalidiert. V4-only (Opt-in-Parameter).
  const { daten, loading, error, refresh } = useAggregierteDaten(anlageId ?? undefined, undefined, 'v4-ausw-basis')
  const { strompreis } = useAktuellerStrompreis(anlageId ?? null)
  const { strompreise: alleTarife } = useStrompreise(anlageId ?? undefined)
  const [jahr, setJahr] = useState<number | 'alle'>('alle')

  const jahre = useMemo(
    () => [...new Set(daten.map((d) => d.jahr))].sort((a, b) => b - a),
    [daten],
  )
  const gefiltert = useMemo(
    () => (jahr === 'alle' ? daten : daten.filter((d) => d.jahr === jahr)),
    [daten, jahr],
  )
  const stats = useAggregierteStats(gefiltert)
  const zeitraumLabel = useMemo(() => zeitraumLabelFuer(jahr, jahre), [jahr, jahre])

  return { daten, gefiltert, stats, strompreis, alleTarife, jahr, setJahr, jahre, zeitraumLabel, loading, error, refresh }
}
