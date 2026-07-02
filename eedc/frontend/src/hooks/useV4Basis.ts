import { useLocation } from 'react-router-dom'

/**
 * V4-Präfix für Cross-Links aus GETEILTEN `pages/*Teile.tsx`.
 *
 * Die geteilten Verwaltungs-Komponenten (Investitionen, Monatsdaten, …) rendern in
 * BEIDEN Welten: der V3-Seite (`#/einstellungen/…`) und dem IA-V4-Einstellungs-Block
 * (`#/v4/einstellungen/…`). Ein hart kodierter Hash-Link kann nicht für beide stimmen
 * → dieser Hook liefert den Präfix **route-abhängig** (`''` in V3, `'/v4'` unter
 * `/v4/…`). So bleibt EINE Code-Wahrheit, ohne dass V4 in eine V3-Seite (Sackgasse
 * ohne Rückweg) verlinkt.
 *
 * ⚠️ NUR anwendbar, wenn die Ziel-**Unterseite** in V3 und V4 gleich heißt (z. B.
 * `einstellungen/infothek` → `v4/einstellungen/infothek`). Re-kategorisierte Ziele
 * (V3 `einstellungen/monatsdaten`/`daten-checker` → V4 `einstellungen/daten`) brauchen
 * ein echtes Routen-Mapping, kein reines Präfix (s. `PLAN-IA-V4-RESTWEG.md` §2b).
 */
export function useV4Basis(): '' | '/v4' {
  const { pathname } = useLocation()
  return pathname.startsWith('/v4') ? '/v4' : ''
}
