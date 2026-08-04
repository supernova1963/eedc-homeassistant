/**
 * Cockpit/Jahr + Monat — die SOLL-Erfüllung erbt das gekürzte Fenster (N-69).
 *
 * Das Backend kürzt den SOLL-Nenner des laufenden Monats auf die abgelaufenen
 * Tage. Das Jahr entsteht als Σ der Monatszeilen — es erbt die Korrektur also
 * nur, wenn `baueJahrAlsMonat` die Fenster-Felder **mitsummiert**. Genau das
 * sichert dieser Beleg, dazu die Kachel-Tooltips beider Sichten.
 *
 * Zahlen: Messung an Gernots Anlage (Winterborn) am 2026-08-04 — Jan–Jul voll,
 * August 4 von 31 Tagen.
 */
import { describe, it, expect } from 'vitest'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import { baueJahrAlsMonat } from './JahrAggregat'
import { baueJahrKpis } from './JahrBilanz'
import { baueMonatKpis } from './MonatBilanz'
import { sollErfuellungProzent, sollFensterText } from '../lib/sollErfuellung'

const monat = (m: number, felder: Partial<AktuellerMonatResponse>): AktuellerMonatResponse => ({
  anlage_id: 1, anlage_name: 'Winterborn', jahr: 2026, monat: m, monat_name: String(m),
  aktualisiert_um: '', quellen: {},
  ...felder,
} as unknown as AktuellerMonatResponse)

const SOLL_JAN_JUL = [396.1, 615.7, 1052.7, 1411.8, 1466.2, 1477.2, 1509.0]
const IST_JAN_JUL = [330.11, 545.41, 1439.9, 1786.5, 1751.3, 1753.8, 1843.25]
const TAGE_JAN_JUL = [31, 28, 31, 30, 31, 30, 31]

const jahr2026 = () => baueJahrAlsMonat([
  ...SOLL_JAN_JUL.map((soll, i) => monat(i + 1, {
    soll_pv_kwh: soll, pv_erzeugung_kwh: IST_JAN_JUL[i],
    soll_pv_tage: TAGE_JAN_JUL[i], soll_pv_tage_gesamt: TAGE_JAN_JUL[i],
  })),
  monat(8, { soll_pv_kwh: 179.1, pv_erzeugung_kwh: 264.75, soll_pv_tage: 4, soll_pv_tage_gesamt: 31 }),
], 2026)

describe('baueJahrAlsMonat — SOLL-Fenster', () => {
  it('summiert die Tage wie die SOLL-Menge', () => {
    const jahr = jahr2026()
    expect(jahr.soll_pv_tage).toBe(216)        // 212 volle + 4 Augusttage
    expect(jahr.soll_pv_tage_gesamt).toBe(243) // 212 + 31
    expect(jahr.soll_pv_kwh).toBeCloseTo(8107.8, 1)
  })

  it('führt zur gemessenen Jahresquote statt zu den alten 104 %', () => {
    const jahr = jahr2026()
    expect(Math.round(sollErfuellungProzent(jahr)!)).toBe(120) // 119,8 %
    expect(sollFensterText(jahr)).toBe('anteilig · 216 von 243 Tagen')
  })
})

describe('Kachel-Tooltips', () => {
  const pv = (items: ReturnType<typeof baueJahrKpis>) =>
    items.find((k) => k.title === 'PV-Erzeugung')!

  it('nennt das Fenster im Jahr', () => {
    const k = pv(baueJahrKpis(jahr2026(), null))
    expect(k.subtitle).toContain('SOLL')
    expect(k.berechnung).toContain('anteilig · 216 von 243 Tagen')
    expect(k.formel).toBe('PV-Ertrag ÷ PVGIS-SOLL × 100')
  })

  it('nennt das Fenster im laufenden Monat', () => {
    const k = pv(baueMonatKpis(
      monat(8, { soll_pv_kwh: 179.1, pv_erzeugung_kwh: 264.75, soll_pv_tage: 4, soll_pv_tage_gesamt: 31 }),
      null,
    ))
    expect(k.subtitle).toBe('SOLL 179 kWh · 148 %')
    expect(k.berechnung).toContain('anteilig · 4 von 31 Tagen')
  })

  it('schweigt über das Fenster im abgeschlossenen Monat', () => {
    const k = pv(baueMonatKpis(
      monat(7, { soll_pv_kwh: 1509, pv_erzeugung_kwh: 1843.25, soll_pv_tage: 31, soll_pv_tage_gesamt: 31 }),
      null,
    ))
    expect(k.subtitle).toBe('SOLL 1.509 kWh · 122 %')
    expect(k.berechnung).not.toContain('anteilig')
  })
})
