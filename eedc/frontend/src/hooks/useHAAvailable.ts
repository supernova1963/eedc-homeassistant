/**
 * Hooks zur Erkennung, wie eedc mit Home Assistant verbunden ist.
 *
 * **Zwei Fragen, zwei Hooks (N-237):**
 * - `useHAAvailable()` — läuft eedc als **Add-on**? (`ha_integration_available`,
 *   = Supervisor-Token). Daran hängt, was ohne Supervisor gar nicht existiert.
 * - `useHAVerbunden()` — ist **irgendeine** HA-Instanz erreichbar? (`ha_verbunden`,
 *   Supervisor **oder** Long-Lived-Token). Daran hängt alles, was nur lesen will.
 *
 * Bis 2026-08-11 gab es nur die erste Frage, und sie beantwortete auch die zweite:
 * Ein Container mit Token-Anbindung galt als „kein HA" und bekam den
 * Statistik-Import nicht zu sehen, obwohl seine Verbindung ihn tragen kann.
 *
 * WICHTIG: Verwendet relativen Pfad './api' für HA Ingress Kompatibilität!
 * Absoluter Pfad '/api' würde in HA Ingress auf die HA-API zeigen.
 */

import { useState, useEffect } from 'react'
import { api } from '../api/client'

type SettingsFlags = {
  ha_integration_available?: boolean
  ha_verbunden?: boolean
}

let cachedResult: boolean | null = null
let cachedVerbunden: boolean | null = null

function useSettingsFlag(
  lies: (data: SettingsFlags) => boolean,
  cache: 'addon' | 'verbunden',
): boolean {
  const start = cache === 'addon' ? cachedResult : cachedVerbunden
  const [wert, setWert] = useState<boolean>(start ?? false)

  useEffect(() => {
    const vorhanden = cache === 'addon' ? cachedResult : cachedVerbunden
    if (vorhanden !== null) return

    api.get<SettingsFlags>('/settings')
      .then(data => {
        // Beide Antworten stammen aus derselben Abfrage — der zweite Hook
        // kostet dadurch keinen zusätzlichen Request.
        cachedResult = data.ha_integration_available ?? false
        cachedVerbunden = data.ha_verbunden ?? cachedResult
        setWert(lies(data) ?? false)
      })
      .catch(() => {
        cachedResult = false
        cachedVerbunden = false
        setWert(false)
      })
  }, [])

  return wert
}

/** Läuft eedc als HA-Add-on (Supervisor-Token vorhanden)? */
export function useHAAvailable(): boolean {
  return useSettingsFlag(d => d.ha_integration_available ?? false, 'addon')
}

/** Ist eine HA-Instanz erreichbar — als Add-on **oder** per Long-Lived-Token? */
export function useHAVerbunden(): boolean {
  return useSettingsFlag(
    d => d.ha_verbunden ?? d.ha_integration_available ?? false,
    'verbunden',
  )
}
