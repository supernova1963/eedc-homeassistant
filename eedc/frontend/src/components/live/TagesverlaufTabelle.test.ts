/**
 * tagesverlaufTabelle (Paket CT) — Tabellen-Ablesung des Live-Butterfly:
 * bidirektionale Serien bleiben EINE Vorzeichen-Spalte (kein _pos/_neg-Split),
 * Overlays behalten ihre Einheit + null-Lücken, Quellen/Senken fehlend → 0.
 */
import { describe, it, expect } from 'vitest'
import { tagesverlaufTabelle } from './TagesverlaufChart'
import type { TagesverlaufSerie, TagesverlaufPunkt } from '../../api/liveDashboard'

const SERIEN: TagesverlaufSerie[] = [
  { key: 'pv_1', label: 'PV Süd', kategorie: 'pv', farbe: '#000', seite: 'quelle', bidirektional: false },
  { key: 'batterie_2', label: 'BYD HVS', kategorie: 'batterie', farbe: '#000', seite: 'quelle', bidirektional: true },
  { key: 'preis', label: 'Strompreis', kategorie: 'preis', farbe: '#000', seite: 'overlay', bidirektional: false, einheit: 'ct/kWh' },
]

const PUNKTE: TagesverlaufPunkt[] = [
  { zeit: '10:00', werte: { pv_1: 3.2, batterie_2: -1.5, preis: 24.31 } },
  { zeit: '10:10', werte: { batterie_2: 0.8 } }, // pv fehlt → 0, preis fehlt → null
]

describe('tagesverlaufTabelle — Paket CT', () => {
  it('1 Spalte je Backend-Serie: kW-Default, Overlay-Einheit bleibt', () => {
    const { spalten } = tagesverlaufTabelle(SERIEN, PUNKTE)
    expect(spalten.map((s) => s.key)).toEqual(['pv_1', 'batterie_2', 'preis'])
    expect(spalten[0].einheit).toBe('kW')
    expect(spalten[2].einheit).toBe('ct/kWh')
  })

  it('bidirektionale Serie = EINE Spalte mit Vorzeichen (kein _pos/_neg)', () => {
    const { daten } = tagesverlaufTabelle(SERIEN, PUNKTE)
    expect(daten[0].batterie_2).toBe(-1.5)
    expect(daten[1].batterie_2).toBe(0.8)
  })

  it('fehlende Werte: Quellen/Senken → 0 (wie Chart-Fläche), Overlay → null (Lücke)', () => {
    const { daten } = tagesverlaufTabelle(SERIEN, PUNKTE)
    expect(daten[1].pv_1).toBe(0)
    expect(daten[1].preis).toBeNull()
    expect(daten[0].zeit).toBe('10:00')
  })
})
