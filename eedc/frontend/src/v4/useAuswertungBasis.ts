/**
 * useAuswertungBasis — gemeinsamer Daten-/Zeitraum-Sockel der monatsdaten-
 * basierten Auswertungen-Sub-Sichten (CO₂, Finanzen, Prognose). Lädt die
 * aggregierten Monatsdaten EINMAL (alle Jahre), hält den Jahr-Filter +
 * abgeleitete Stats + Zeitraum-Label und reicht Strompreis + Tarif-Historie
 * durch. Eine Code-Wahrheit: gleicher Lade-/Aggregations-Pfad wie die IST-Seite
 * `Auswertung.tsx` (ADR-001, kein neuer Endpoint), client-seitige Jahr-Filterung
 * (Tab-Wechsel ohne Refetch).
 *
 * R18-3 (Option B): Der Hook wird EINMAL im Dispatcher (`AuswertungenV4`)
 * aufgerufen und als `basis`-Prop an die Sub-Sichten gereicht (Community-Muster
 * `CommunityV4`). Dadurch überlebt die Jahr-Auswahl den Sub-Tab-Wechsel und es
 * gibt genau EINE Filter-Wahrheit. `statsGesamt` (ungefiltert) existiert für
 * Blöcke, die dem Jahr-Filter inhaltlich nicht folgen können (CO₂-Amortisation
 * gegen die graue Last der GESAMTEN Historie, R18-3c).
 */
import { useEffect, useMemo, useState } from 'react'
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
  // Anlagen-Wechsel-Guard (R18-3d): Die Auswahl lebt jetzt dispatcher-lang —
  // existiert das gewählte Jahr in der neuen Anlage nicht, zurück auf „Alle Jahre"
  // (vorher erledigte das der Remount je Sub-Sicht implizit).
  useEffect(() => {
    if (!loading && jahr !== 'alle' && jahre.length > 0 && !jahre.includes(jahr)) setJahr('alle')
  }, [loading, jahr, jahre])

  const gefiltert = useMemo(
    () => (jahr === 'alle' ? daten : daten.filter((d) => d.jahr === jahr)),
    [daten, jahr],
  )
  const stats = useAggregierteStats(gefiltert)
  const statsGesamt = useAggregierteStats(daten)
  const zeitraumLabel = useMemo(() => zeitraumLabelFuer(jahr, jahre), [jahr, jahre])

  return { daten, gefiltert, stats, statsGesamt, strompreis, alleTarife, jahr, setJahr, jahre, zeitraumLabel, loading, error, refresh }
}

/** Prop-Typ der Sub-Sichten: der EINE Basis-Sockel aus dem Dispatcher. */
export type AuswertungBasis = ReturnType<typeof useAuswertungBasis>
