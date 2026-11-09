/**
 * „Alle Jahre" in der PV-String-Sicht — die Zeilen sind nicht in jedem Jahr dieselben (N-613).
 *
 * Seit die Abtretung eines Balkonkraftwerks an seine Modul-Kinder je Monat gilt,
 * hat ein BKW, dem später Module zugeordnet wurden, eine eigene Zeile nur in den
 * Jahren, in denen es noch selbst trägt. Der Client-Pfad „alle Jahre" baute seine
 * Zeilen aus dem ERSTEN Jahr der Liste — eine Zeile, die dort fehlt, fiel mit
 * ihrer Erzeugung aus dem Gesamtwert.
 *
 * Päckchen BB4 (9.11.2026): „alle Jahre" liest die Laufzeit-Route; ihre Zeilen sind die Träger der ganzen Laufzeit
 * (Backend-Probe `test_n613_pv_strings_abtretung_je_monat.py`). Hier: der Adapter reicht Zeilen, Summen, Monatsverlauf
 * und spezifischen Ertrag unverändert durch (keine Rechnung), und der Mehrjahres-Chart liest weiter die Jahre.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

const getPVStrings = vi.fn()
const getPVStringsGesamtlaufzeit = vi.fn()
vi.mock('../../api/cockpit', () => ({ cockpitApi: {
  getPVStrings: (...a: unknown[]) => getPVStrings(...a),
  getPVStringsGesamtlaufzeit: (...a: unknown[]) => getPVStringsGesamtlaufzeit(...a),
} }))

import { usePvStrings } from './PvStringsTeile'
import type { PVStringsResponse, PVStringGesamtlaufzeit } from '../../api/cockpit'

const zeile = (id: number, bezeichnung: string, kwp: number, soll: number, ist: number) => ({
  investition_id: id, bezeichnung, leistung_kwp: kwp, ausrichtung: null, neigung_grad: null,
  wechselrichter_id: null, wechselrichter_name: null,
  prognose_jahr_kwh: soll, ist_jahr_kwh: ist, abweichung_jahr_kwh: ist - soll,
  abweichung_jahr_prozent: null, performance_ratio_jahr: soll > 0 ? ist / soll : null,
  spezifischer_ertrag_kwh_kwp: ist / kwp, ist_quelle: 'gemessen' as const, monatswerte: [],
})

const antwort = (jahr: number, strings: PVStringsResponse['strings']): PVStringsResponse => ({
  anlage_id: 1, jahr, hat_prognose: true, prognose_warnung: null, anlagen_leistung_kwp: 0.8,
  prognose_gesamt_kwh: strings.reduce((s, x) => s + x.prognose_jahr_kwh, 0),
  ist_gesamt_kwh: strings.reduce((s, x) => s + x.ist_jahr_kwh, 0),
  abweichung_gesamt_kwh: 0, abweichung_gesamt_prozent: null, strings,
  bester_string: null, schlechtester_string: null, ist_quelle: 'gemessen', vergleich_hinweis: null,
})

// Die Jahresreihenfolge der Seite ist absteigend (neueste zuerst) — das BKW steht
// nur im ÄLTEREN Jahr und damit gerade NICHT im ersten der Liste.
const JAHRE = [2026, 2025]

beforeEach(() => vi.clearAllMocks())

const lzZeile = (id: number, bezeichnung: string, kwp: number, soll: number, ist: number): PVStringGesamtlaufzeit => ({
  investition_id: id, bezeichnung, leistung_kwp: kwp, ausrichtung: null, neigung_grad: null, wechselrichter_name: null,
  prognose_gesamt_kwh: soll, ist_gesamt_kwh: ist, abweichung_gesamt_prozent: -93, performance_ratio_gesamt: 0.07,
  spezifischer_ertrag_kwh_kwp: 88, ist_quelle: 'gemessen', jahreswerte: [], saisonalwerte: [],
  abweichung_gesamt_kwh: ist - soll,
  monatswerte_summe: [{ monat: 5, monat_name: 'Mai', prognose_summe_kwh: soll, ist_summe_kwh: ist }],
})

describe('usePvStrings — „alle Jahre" mit einer Zeile, die nicht in jedem Jahr steht', () => {
  it('nimmt die Zeilen und Summen der Laufzeit-Route — das Balkonkraftwerk aus dem früheren Jahr steht drin', async () => {
    getPVStrings.mockImplementation((_id: number, jahr: number) => Promise.resolve(
      jahr === 2025
        ? antwort(2025, [zeile(1, 'Balkon', 0.8, 1000, 70), zeile(2, 'Kind 1', 0.4, 0, 0), zeile(3, 'Kind 2', 0.4, 0, 0)])
        : antwort(2026, [zeile(2, 'Kind 1', 0.4, 500, 35), zeile(3, 'Kind 2', 0.4, 500, 35)])))
    getPVStringsGesamtlaufzeit.mockResolvedValue({
      anlage_id: 1, hat_prognose: true, prognose_warnung: null, anlagen_leistung_kwp: 0.8,
      erstes_jahr: 2025, letztes_jahr: 2026, anzahl_jahre: 2, anzahl_monate: 2,
      prognose_gesamt_kwh: 2000, ist_gesamt_kwh: 140, abweichung_gesamt_kwh: -1860, abweichung_gesamt_prozent: -93,
      spezifischer_ertrag_zeitraum_kwh_kwp: 175,
      strings: [lzZeile(1, 'Balkon', 0.8, 1000, 70), lzZeile(2, 'Kind 1', 0.4, 500, 35), lzZeile(3, 'Kind 2', 0.4, 500, 35)],
      saisonal_aggregiert: [], bester_string: null, schlechtester_string: null, ist_quelle: 'gemessen',
      vergleich_hinweis: null,
    })
    const { result } = renderHook(() => usePvStrings(1, 'all', JAHRE))
    await waitFor(() => expect(result.current.loading).toBe(false))
    const data = result.current.data
    expect(data?.ist_gesamt_kwh).toBe(140)
    expect(data?.prognose_gesamt_kwh).toBe(2000)
    expect(data?.spezifischer_ertrag_kwh_kwp).toBe(175)
    expect(data?.strings.map((s) => s.bezeichnung)).toEqual(['Balkon', 'Kind 1', 'Kind 2'])
    const balkon = data?.strings.find((s) => s.bezeichnung === 'Balkon')
    expect([balkon?.ist_jahr_kwh, balkon?.prognose_jahr_kwh, balkon?.abweichung_jahr_kwh]).toEqual([70, 1000, -930])
    expect(balkon?.monatswerte).toEqual([{ monat: 5, monat_name: 'Mai', prognose_kwh: 1000, ist_kwh: 70,
      abweichung_kwh: null, abweichung_prozent: null, performance_ratio: null, ist_quelle: 'gemessen' }])
    // Der Mehrjahres-Chart (Block ③) liest weiter die Jahres-Antworten selbst.
    expect(getPVStrings).toHaveBeenCalledTimes(2)
    expect(result.current.jahresvergleichData.map((e) => e.jahr)).toEqual([2025, 2026])
  })
})
