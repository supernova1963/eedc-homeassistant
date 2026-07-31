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
 *
 * **N-21 (2026-07-31): die CO₂-Reihe gehört in den Sockel, nicht in die Sicht.**
 * Die Auswertungen rechneten CO₂ bis dahin selbst — `erzeugung × 0,38` im
 * Client, an zwei Stellen (CO₂-Sicht und Werte-Tabelle). Das war eine
 * Aggregat-Formel außerhalb des Berechnungs-Layers (ADR-001) **und** die vor
 * `berechne_co2_bilanz` gültige Definition: sie schrieb der eingespeisten kWh
 * die volle Netzstrom-Vermeidung gut und kannte weder WP noch E-Mobilität.
 * Gerechnet wird jetzt nirgends mehr — geladen wird `/cockpit/nachhaltigkeit`,
 * derselbe Endpoint, aus dem der Block „CO₂-Bilanz" in Cockpit/Jahr liest.
 * Hier im Sockel, weil ihn ZWEI Sub-Sichten brauchen (CO₂ + Tabelle) und der
 * Sockel genau dafür da ist (Paket Q: ein Abruf statt eines pro Sicht).
 *
 * Der Fehlerzustand bleibt bewusst **getrennt** von `error`: fällt die CO₂-Reihe
 * aus, dürfen Finanzen und Prognose trotzdem laden.
 */
import { useEffect, useMemo, useState } from 'react'
import { useAggregierteDaten, useAggregierteStats, useAktuellerStrompreis, useStrompreise, useApiData } from '../hooks'
import { cockpitApi, type Nachhaltigkeit } from '../api/cockpit'

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

  // Kanonische CO₂-Reihe (ADR-001/DI-2). EIN Abruf für CO₂-Sicht + Werte-Tabelle.
  const co2Q = useApiData<Nachhaltigkeit>(
    () => cockpitApi.getNachhaltigkeit(anlageId!),
    [anlageId],
    { enabled: !!anlageId, swrKey: `v4-ausw-co2:${anlageId}` },
  )
  const co2 = useMemo(() => ({
    /** Alle Monate der GESAMTEN Historie, aufsteigend (der Endpoint kennt kein `?jahr=`). */
    monate: co2Q.data?.monatswerte ?? [],
    /** Σ der gesamten Historie — die Zahl, die der Endpoint selbst ausweist. */
    gesamtKg: co2Q.data?.co2_gesamt_kg ?? 0,
    loading: co2Q.loading,
    error: co2Q.error,
    refresh: co2Q.refetch,
  }), [co2Q.data, co2Q.loading, co2Q.error, co2Q.refetch])

  return { daten, gefiltert, stats, statsGesamt, strompreis, alleTarife, jahr, setJahr, jahre, zeitraumLabel, loading, error, refresh, co2 }
}

/** Prop-Typ der Sub-Sichten: der EINE Basis-Sockel aus dem Dispatcher. */
export type AuswertungBasis = ReturnType<typeof useAuswertungBasis>
