/**
 * Cockpit/Jahr + Monat — die SOLL-Erfüllung erbt das gekürzte Fenster (N-69).
 *
 * Das Backend kürzt den SOLL-Nenner des laufenden Monats auf die abgelaufenen
 * Tage. Das Jahr entsteht seit 03.10.2026 im Backend (`falte_zeitraum`); dass es die
 * Fenster-Felder mitsummiert und die Quote daraus bildet, prüft
 * `backend/tests/test_ergebnis_jahr_portiert.py::test_soll_*` mit denselben Zahlen.
 * Hier bleiben die Kachel-Tooltips beider Sichten — sie LESEN Quote und Fenster
 * aus der Antwort (`soll_erfuellung_prozent`, `soll_fenster_text`).
 *
 * Zahlen: Messung an Gernots Anlage (Winterborn) am 2026-08-04 — Jan–Jul voll,
 * August 4 von 31 Tagen.
 */
import { describe, it, expect } from 'vitest'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import { baueJahrKpis } from './JahrBilanz'
import { baueMonatKpis } from './MonatBilanz'
import { aktuellerMonat } from '../test/factories'

const monat = (m: number, felder: Partial<AktuellerMonatResponse>) =>
  aktuellerMonat(2026, m, { anlage_name: 'Winterborn', monat_name: String(m), ...felder })

// Das Jahr, wie die Jahresroute es liefert (Winterborn 04.08.2026: Jan–Jul voll, August 4 von 31 Tagen) —
// Σ SOLL 8.107,8 kWh, Σ IST 9.714,27 kWh, Quote 119,8 %, Fenster 216 von 243 Tagen.
const jahr2026 = () => aktuellerMonat(2026, 0, {
  monat_name: '2026', soll_pv_kwh: 8107.8, pv_erzeugung_kwh: 9714.27,
  soll_pv_tage: 216, soll_pv_tage_gesamt: 243,
  soll_erfuellung_prozent: (9714.27 / 8107.8) * 100, soll_fenster_text: 'anteilig · 216 von 243 Tagen',
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
      monat(8, {
        soll_pv_kwh: 179.1, pv_erzeugung_kwh: 264.75, soll_pv_tage: 4, soll_pv_tage_gesamt: 31,
        soll_erfuellung_prozent: (264.75 / 179.1) * 100, soll_fenster_text: 'anteilig · 4 von 31 Tagen',
      }),
      null,
    ))
    expect(k.subtitle).toBe('SOLL 179 kWh · 148 %')
    expect(k.berechnung).toContain('anteilig · 4 von 31 Tagen')
  })

  it('schweigt über das Fenster im abgeschlossenen Monat', () => {
    const k = pv(baueMonatKpis(
      monat(7, {
        soll_pv_kwh: 1509, pv_erzeugung_kwh: 1843.25, soll_pv_tage: 31, soll_pv_tage_gesamt: 31,
        soll_erfuellung_prozent: (1843.25 / 1509) * 100, soll_fenster_text: null,
      }),
      null,
    ))
    expect(k.subtitle).toBe('SOLL 1.509 kWh · 122 %')
    expect(k.berechnung).not.toContain('anteilig')
  })
})
