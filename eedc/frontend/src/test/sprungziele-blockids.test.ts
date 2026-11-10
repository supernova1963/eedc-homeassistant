/**
 * Etappe E2 «Daten-Checker: ein Handgriff je Befund» (Bauplan §4, Spiegel-Test vor W-5 in E4): der Ziel-Bauer des
 * Backends (`services/daten_checker/ziele.py`) prüft jede Block-Id gegen seine Tabelle `BLOCK_IDS`. Die Tabelle ist
 * wörtlich der Einstellungs-Katalog — diese Probe hält beide gleich, damit keine zweite Wahrheit stehen bleibt.
 */
import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

import { EINSTELLUNGEN_KATALOG, EINSTELLUNGEN_KATEGORIEN } from '../config/einstellungenKatalog'

/** SoT des Ziel-Bauers — im SoT-Repo wie im Standalone-Spiegel unter `eedc/`. */
const ZIELE_QUELLE = '../backend/services/daten_checker/ziele.py'

function backendBlockIds(): Record<string, string[]> {
  const quelle = readFileSync(ZIELE_QUELLE, 'utf-8')
  const block = quelle.split('BLOCK_IDS: dict[str, tuple[str, ...]] = {')[1]?.split('\n}')[0]
  expect(block, 'BLOCK_IDS in ziele.py nicht gefunden — umbenannt?').toBeTruthy()
  const out: Record<string, string[]> = {}
  for (const m of block.matchAll(/"([a-z-]+)": \(([^)]*)\)/g)) {
    out[m[1]] = [...m[2].matchAll(/"([a-z-]+)"/g)].map((x) => x[1])
  }
  return out
}

describe('Sprungziele: BLOCK_IDS des Backends = Block-Ids des Einstellungs-Katalogs', () => {
  it('jede Kategorie mit genau ihren Blöcken, in Katalog-Reihenfolge', () => {
    const katalog: Record<string, string[]> = {}
    for (const k of EINSTELLUNGEN_KATEGORIEN) katalog[k.key] = []
    for (const e of EINSTELLUNGEN_KATALOG) katalog[e.kategorie].push(e.id)
    expect(backendBlockIds()).toEqual(katalog)
  })
})
