/**
 * useFeldHinweise — Feld-Hilfetexte aus dem Backend-SoT (field_definitions).
 *
 * Lädt /monatsdaten/feld-hinweise einmalig (modul-gecacht, damit
 * mehrere Wizard-Steps nicht je einzeln abrufen) und liefert die Lookup-Map.
 *
 * Lookup-Konvention:
 *   - Investition:  hinweise[inv.typ]?.[feld]          z.B. ['e-auto']['verbrauch_kwh']
 *   - Basis:        hinweise.basis?.[mapping_key]       z.B. ['basis']['einspeisung']
 *   - Sonstiges:    hinweise[`sonstiges:${kategorie}`]?.[feld]
 */
import { useEffect, useState } from 'react'
import { sensorMappingApi, type FeldHinweise } from '../api/sensorMapping'

let cache: FeldHinweise | null = null
let inflight: Promise<FeldHinweise> | null = null

export function useFeldHinweise(): FeldHinweise {
  const [hinweise, setHinweise] = useState<FeldHinweise>(cache ?? {})

  useEffect(() => {
    if (cache) return
    if (!inflight) {
      inflight = sensorMappingApi
        .getFeldHinweise()
        .then(h => {
          cache = h
          return h
        })
        .catch(() => {
          // Hinweise sind rein additiv — bei Fehler still ohne Hinweistexte weiter.
          inflight = null
          return {} as FeldHinweise
        })
    }
    let active = true
    inflight.then(h => {
      if (active) setHinweise(h)
    })
    return () => {
      active = false
    }
  }, [])

  return hinweise
}
