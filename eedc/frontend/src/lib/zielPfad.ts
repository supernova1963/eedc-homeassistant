/**
 * zielPfad — der Pfad eines Sprung-Ziels des Daten-Checkers (Etappe E5: die Antwort trägt seit E5 nur `ziel`, nicht mehr
 * das Altfeld `link`, Wächter W-3).
 *
 * Wörtlich die Regel von `backend/services/daten_checker/kategorien.py::link_aus_ziel`: Komponenten-Hub
 * `/komponenten/<typ>?geraet=<id>`; sonst `/einstellungen/<bereich>` mit `block=` (entfällt, wo `erfassen` den
 * Monatsdaten-Block selbst aufklappt) und den Parametern des Schemas in fester Reihenfolge. Kein zweiter Ort der Regel:
 * der Vitest `zielPfad.test.ts` vergleicht jedes Ziel des Backend-Exports `tests/fixtures/sprungziele.json` (Abschnitt
 * `pfade`) mit dem Pfad, den das Backend gebildet hat.
 */
import type { CheckZiel } from '../api/datenChecker'

/** Reihenfolge der Parameter im Pfad (`kategorien.ZIEL_PARAMETER`). */
export const ZIEL_PARAMETER = ['erfassen', 'bearbeiten', 'neu', 'tarif', 'art', 'ab', 'geraet', 'feld', 'karte', 'plan', 'wizard']

export function zielPfad(ziel: CheckZiel | null | undefined): string | null {
  if (!ziel) return null
  const p = ziel.params ?? {}
  if (ziel.bereich === 'komponenten-hub') return `/komponenten/${ziel.block}?geraet=${String(p.geraet)}`
  const teile = ziel.block && !('erfassen' in p) ? [`block=${ziel.block}`] : []
  for (const k of ZIEL_PARAMETER) {
    if (p[k] !== undefined && p[k] !== null) teile.push(`${k}=${String(p[k])}`)
  }
  return `/einstellungen/${ziel.bereich}${teile.length ? `?${teile.join('&')}` : ''}`
}
