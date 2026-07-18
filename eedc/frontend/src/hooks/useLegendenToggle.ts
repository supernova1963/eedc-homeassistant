import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { LegendEintrag } from '../components/ui/ChartLegende'

/**
 * useLegendenToggle — SoT der Legenden-Toggle-Mechanik (Style-Guide B7,
 * Gernot-Entscheid 2026-07-08: Standard für JEDEN Chart mit > 1 Serie).
 *
 * Klick auf einen `ChartLegende`-Eintrag blendet die Serie aus/ein: der Chart
 * setzt `hide={istVersteckt(key)}` am Series-Element (Bar/Line/Area/Radar),
 * Recharts dimmt den Legenden-Eintrag (`inactive`) und reskaliert die Y-Achse
 * auf die sichtbaren Serien — löst Größenordnungs-Lesbarkeit (PV ~20× BKW).
 *
 * Zustand ist bewusst flüchtig (KEINE C4-Persistenz) und resettet bei
 * `resetSignal`-Wechsel (Modus/Preset — der Serien-Satz ändert sich, alte
 * Versteck-Keys wären stale). Kein Mindest-Sichtbar-Zwang: alles ist
 * ausblendbar, der Klick auf den gedimmten Eintrag holt die Serie zurück.
 *
 *   const legende = useLegendenToggle(view)
 *   <Legend content={<ChartLegende onItemClick={legende.onItemClick} />} />
 *   <Bar dataKey="einspeisung" hide={legende.istVersteckt('einspeisung')} … />
 *
 * Key-Wahl bleibt chart-lokal: Default ist `dataKey` (via `onItemClick`);
 * Sonderfälle (Name-Key bei doppeltem dataKey, Paar-Mapping ± im Butterfly)
 * verdrahten `toggleSerie` direkt mit eigenem Mapping.
 */
export function useLegendenToggle(resetSignal?: unknown) {
  const [versteckt, setVersteckt] = useState<ReadonlySet<string>>(new Set())

  // Reset NUR bei echtem Wechsel des Signals (nicht beim Mount-Render).
  const vorher = useRef(resetSignal)
  useEffect(() => {
    if (Object.is(vorher.current, resetSignal)) return
    vorher.current = resetSignal
    setVersteckt(new Set())
  }, [resetSignal])

  const toggleSerie = useCallback((key: string) => {
    setVersteckt((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  const onItemClick = useCallback(
    (e: LegendEintrag) => toggleSerie(String(e.dataKey ?? e.value)),
    [toggleSerie],
  )

  const istVersteckt = useCallback((key: string) => versteckt.has(key), [versteckt])

  // Identitäts-stabil (wechselt nur beim Toggle): Konsumenten dürfen das Objekt
  // gefahrlos in useMemo-Deps legen (z. B. memoisierte Block-render-Closures).
  return useMemo(
    () => ({ versteckt, toggleSerie, onItemClick, istVersteckt }),
    [versteckt, toggleSerie, onItemClick, istVersteckt],
  )
}
