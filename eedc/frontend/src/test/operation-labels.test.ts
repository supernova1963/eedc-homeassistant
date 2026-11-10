/**
 * Etappe E3 «Daten-Checker: ein Handgriff je Befund» (Auftrag E3.2; Beobachtung Päckchen GG): die Namen der
 * Reparatur-Operationen stehen an zwei Stellen — `OPERATION_META` der Werkbank (hier) und
 * `backend/services/repair_protokoll.py::OPERATION_LABELS` (die Zeile im Aktivitätsprotokoll). Diese Probe hält beide
 * wörtlich gleich, damit Werkbank und Protokolle dieselbe Operation gleich nennen.
 */
import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

import { OPERATION_META } from '../api/repair'

const PROTOKOLL_QUELLE = '../backend/services/repair_protokoll.py'

function backendLabels(): Record<string, string> {
  const quelle = readFileSync(PROTOKOLL_QUELLE, 'utf-8')
  const block = quelle.split('OPERATION_LABELS = {')[1]?.split('\n}')[0]
  expect(block, 'OPERATION_LABELS in repair_protokoll.py nicht gefunden — umbenannt?').toBeTruthy()
  return Object.fromEntries([...block.matchAll(/"([a-z_]+)": "([^"]+)"/g)].map((m) => [m[1], m[2]]))
}

describe('Reparatur-Operationen: Werkbank und Protokoll nennen sie gleich', () => {
  it('jede Operation des Protokolls steht mit demselben Namen in OPERATION_META', () => {
    const backend = backendLabels()
    const client = Object.fromEntries(OPERATION_META.map((o) => [o.type, o.label]))
    expect(Object.keys(backend).length).toBeGreaterThanOrEqual(13)
    for (const [typ, label] of Object.entries(backend)) {
      expect(client[typ], `${typ} fehlt in OPERATION_META`).toBe(label)
    }
    // Umgekehrt: jede Operation der Werkbank außer dem Stub hat einen Protokoll-Namen.
    const ohne = OPERATION_META.filter((o) => o.type !== 'solcast_rewrite' && !(o.type in backend)).map((o) => o.type)
    expect(ohne).toEqual([])
  })
})
