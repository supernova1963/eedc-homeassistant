/**
 * Die Kategorie-Liste ist ein **Filter**, kein Sortier-Wunsch.
 *
 * `pages/DatenCheckerTeile.tsx` rendert `KATEGORIE_REIHENFOLGE.map(...)` — eine
 * Backend-Kategorie, die dort fehlt, erscheint auf der Daten-Checker-Seite
 * **gar nicht**, auch wenn das Backend sie liefert und der Befund einen
 * Reparatur-Knopf trägt.
 *
 * ⚠ **Genau das war F-21** (10.08.): `emob_doppelzaehlung_tage` — eine WARNING
 * mit „Zeitraum neu aggregieren", der Reparaturpfad zu N-186 — stand seit
 * ihrem Bau in keiner der beiden Listen und war damit unerreichbar;
 * `phev_anteil_unbestimmt` ebenso (nur über `investition_id` im
 * Komponenten-Hub sichtbar). Gefunden wurde beides erst, als Bauschritt 8 zwei
 * **neue** Kategorien einhängte — es wäre sonst wieder passiert.
 *
 * Deshalb prüft diese Probe nicht mehr die zwei neuen Kategorien einzeln,
 * sondern **jede** aus dem Backend-Enum: die Klasse wird gewächtert, nicht der
 * Einzelfall ([[konzept-fundverwaltung]] Teil 3).
 */
import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

import { KATEGORIE_LABELS, KATEGORIE_REIHENFOLGE } from './datenCheckerKategorien'

/** SoT der Kategorien — im SoT-Repo wie im Standalone-Spiegel unter `eedc/`. */
const ENUM_QUELLE = '../backend/services/daten_checker/kategorien.py'

/**
 * Die Werte aus `class CheckKategorie`. Bewusst nur dieser Block: `kategorien.py`
 * definiert direkt darüber `CheckSeverity` mit demselben Zeilenmuster, und ein
 * Grep über die ganze Datei hielte „error"/„warning" für Kategorien.
 */
function backendKategorien(): string[] {
  const quelle = readFileSync(ENUM_QUELLE, 'utf-8')
  const block = quelle.split('class CheckKategorie')[1]?.split('\n@dataclass')[0]
  expect(block, 'class CheckKategorie nicht gefunden — Datei umbenannt?').toBeTruthy()
  return [...block.matchAll(/^\s{4}[A-Z_]+ = "([a-z_]+)"/gm)].map((m) => m[1])
}

describe('Daten-Checker-Kategorien: keine unsichtbaren Befunde (F-21)', () => {
  it('das Backend-Enum ist nicht leer — sonst prüfte diese Datei nichts', () => {
    expect(backendKategorien().length).toBeGreaterThan(20)
  })

  it.each(backendKategorien())('%s hat ein Label und wird gerendert', (kategorie) => {
    expect(KATEGORIE_LABELS[kategorie], `Label fehlt: ${kategorie}`).toBeTruthy()
    // Der eigentliche Punkt: ohne Eintrag hier ist der Befund unerreichbar.
    expect(KATEGORIE_REIHENFOLGE, `nicht gerendert: ${kategorie}`).toContain(kategorie)
  })
})
