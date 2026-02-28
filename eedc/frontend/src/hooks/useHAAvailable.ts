/**
 * Hook zur Erkennung ob Home Assistant Integration verfügbar ist.
 * Prüft den /api/settings Endpoint auf ha_integration_available.
 */

import { useState, useEffect } from 'react'

let cachedResult: boolean | null = null

export function useHAAvailable(): boolean {
  const [available, setAvailable] = useState<boolean>(cachedResult ?? false)

  useEffect(() => {
    if (cachedResult !== null) return

    fetch('/api/settings')
      .then(res => res.json())
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
