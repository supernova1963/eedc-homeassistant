/**
 * Die Wärmepumpen-Spalten heißen in **beiden** Tabellen gleich.
 *
 * Schwesterprobe: `werte.test.ts` (Verhalten der Registry selbst — Aggregation,
 * Format, Granularität). Gegenstand hier ist allein der **Wortlaut** über zwei
 * getrennte Spalten-Listen hinweg.
 *
 * ## Warum es die Probe gibt
 *
 * eedc führt zwei Spalten-SoTs für tabellarische kWh-Werte:
 *
 * - `lib/werte/registry.ts` — *Auswertungen → Tabelle* und die Cockpit-Embeds.
 * - `pages/MonatsdatenTeile.tsx::COLUMNS` — die Pflege-Tabelle unter
 *   *Einstellungen*, mit eigener Datenquelle und eigenen Zeilen-Aktionen.
 *
 * Dass es zwei sind, ist eine bewusste Trennung; dass sie **verschiedene Namen
 * für dieselbe Größe** trugen, war keine. Bis zum 01.09.2026 nannte die
 * Pflege-Tabelle die abgegebene Wärme „WP Heizung"/„WP Warmwasser", die
 * Auswertung dagegen „WP Wärme Heizen"/„WP Wärme WW". Ein Melder (dietmar1968,
 * simon42 T89667 #283) las die thermische Zahl in der ersten Tabelle als
 * eingesetzten Strom — die zweite hätte es ihm gesagt, und ein anderer Tester
 * musste ihn genau dorthin verweisen.
 *
 * ⚠ Die Probe prüft **nicht**, dass beide Tabellen dieselben Spalten führen —
 * das sollen sie gerade nicht. Sie prüft nur: wo beide dieselbe Größe zeigen,
 * steht derselbe Name.
 */
import { describe, it, expect } from 'vitest'
import { WERTE_METRIKEN } from './registry'
import { COLUMNS } from '../../pages/MonatsdatenTeile'

/** Registry-Schlüssel → Spalten-Schlüssel der Pflege-Tabelle. */
const GEMEINSAME_WP_GROESSEN: Record<string, string> = {
  wp_strom: 'wp_strom',
  wp_waerme_heizen: 'wp_heizung',
  wp_waerme_warmwasser: 'wp_warmwasser',
}

describe('WP-Spalten: ein Wortlaut über beide Tabellen', () => {
  it('findet in beiden SoTs überhaupt etwas', () => {
    // Leerlauf-Absicherung: ohne sie liefe die Probe darunter über eine leere
    // Schnittmenge und wäre grün, sobald ein Schlüssel umbenannt wird.
    expect(WERTE_METRIKEN.length).toBeGreaterThan(10)
    expect(COLUMNS.length).toBeGreaterThan(10)
    for (const [regKey, colKey] of Object.entries(GEMEINSAME_WP_GROESSEN)) {
      expect(WERTE_METRIKEN.find((m) => m.key === regKey), `Registry: ${regKey}`).toBeTruthy()
      expect(COLUMNS.find((c) => c.key === colKey), `COLUMNS: ${colKey}`).toBeTruthy()
    }
  })

  it.each(Object.entries(GEMEINSAME_WP_GROESSEN))(
    'Registry %s und Spalte %s tragen denselben Namen',
    (regKey, colKey) => {
      const metrik = WERTE_METRIKEN.find((m) => m.key === regKey)!
      const spalte = COLUMNS.find((c) => c.key === colKey)!
      expect(spalte.label).toBe(metrik.label)
    },
  )

  it('die thermischen Spalten nennen ihre Größe, die elektrische nennt Strom', () => {
    // Zweite Regelhälfte, eigene Prüfung: Der Abgleich oben wäre auch dann
    // grün, wenn BEIDE Listen dieselbe unklare Bezeichnung trügen — genau der
    // Zustand vor dem 01.09.2026 wäre so nicht auffallen.
    const label = (k: string) => COLUMNS.find((c) => c.key === k)!.label
    expect(label('wp_heizung').toLowerCase()).toContain('wärme')
    expect(label('wp_warmwasser').toLowerCase()).toContain('wärme')
    expect(label('wp_strom')).toContain('Strom')
    expect(label('wp_strom').toLowerCase()).not.toContain('wärme')
  })
})
