/**
 * Hook zur Erkennung ob Home Assistant Integration verfügbar ist.
 * Prüft den /api/settings Endpoint auf ha_integration_available.
 *
 * WICHTIG: Verwendet relativen Pfad './api' für HA Ingress Kompatibilität!
 * Absoluter Pfad '/api' würde in HA Ingress auf die HA-API zeigen.
 */

import { useState, useEffect } from 'react'
import { api } from '../api/client'

let cachedResult: boolean | null = null

export function useHAAvailable(): boolean {
  const [available, setAvailable] = useState<boolean>(cachedResult ?? false)

  useEffect(() => {
    if (cachedResult !== null) return

    api.get<{ ha_integration_available?: boolean }>('/settings')
      .then(data => {
        cachedResult = data.ha_integration_available ?? false
        setAvailable(cachedResult!)
      })
      .catch(() => {
        cachedResult = false
        setAvailable(false)
      })
  }, [])

  return available
}
