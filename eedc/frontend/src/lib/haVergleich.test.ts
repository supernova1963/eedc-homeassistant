/**
 * N-534: Dialog „Aus HA laden" — die Zeilen entstehen aus den Feldnamen, die das
 * Backend wirklich liefert (`einspeisung_kwh`), nicht aus den Mapping-Kurzformen.
 * Mit den alten Namen (`einspeisung`) wäre jede Zeile leer — genau das Bild seit v2.5.3.
 *
 * ⚠ N-622: hier stand bis 04.10.2026 eine handgeschriebene Basis mit
 * `{ feld: 'pv_erzeugung_kwh' }` — das Backend sendete `pv_gesamt`, der Dialog zeigte für
 * den PV-Gesamtzähler produktiv immer „–". Die Eingabe ist jetzt die Fixture, die
 * `test_n622_ha_monatswerte_pv_gesamtzaehler.py` bitgleich gegen die Route hält, über den
 * Client-Weg der App (`haStatisticsApi.getMonatswerte`).
 */
import { describe, expect, it, vi } from 'vitest'
import fixture from '../test/ha-monatswerte-n622.fixture.json'
import { haBasisWert, haBasisZeilen } from './haVergleich'

vi.mock('../api/client', () => ({
  api: { get: () => Promise.resolve(structuredClone(fixture)) },
}))

const { haStatisticsApi } = await import('../api/haStatistics')
const backendBasis = (await haStatisticsApi.getMonatswerte(1, 2025, 5)).basis

describe('haBasisZeilen (N-534, N-622)', () => {
  it('liefert je geliefertem Feld eine Zeile mit HA-Wert und lokalem Wert über den DB-Feldnamen', () => {
    const zeilen = haBasisZeilen(backendBasis, { einspeisung_kwh: 399.9, netzbezug_kwh: 200.1, pv_erzeugung_kwh: 990 })
    expect(zeilen).toEqual([
      { feld: 'einspeisung_kwh', label: 'Einspeisung', vorhanden: 399.9, haWert: 400 },
      { feld: 'netzbezug_kwh', label: 'Netzbezug', vorhanden: 200.1, haWert: 200 },
      { feld: 'pv_erzeugung_kwh', label: 'PV Erzeugung Gesamt', vorhanden: 990, haWert: 1000 },
    ])
  })

  it('der PV-Gesamtzähler findet seinen gespeicherten Anlagenwert (bis N-622 stand dort immer „–")', () => {
    const pv = haBasisZeilen(backendBasis, { pv_erzeugung_kwh: 990 }).find((z) => z.label === 'PV Erzeugung Gesamt')
    expect(pv?.vorhanden).toBe(990)
  })

  it('Gegenprobe: die Mapping-Kurzform findet nichts — so entstand das Strich-Bild', () => {
    expect(backendBasis.find((b) => b.feld === 'einspeisung' || b.feld === 'pv_gesamt')).toBeUndefined()
    expect(haBasisWert(backendBasis, 'einspeisung')).toBe('')
    expect(haBasisWert(backendBasis, 'einspeisung_kwh')).toBe('400')
    expect(haBasisWert(backendBasis, 'pv_erzeugung_kwh')).toBe('1000')
  })

  it('verträgt eine fehlende Monatsdaten-Zeile', () => {
    expect(haBasisZeilen(backendBasis, null)[0]).toEqual({ feld: 'einspeisung_kwh', label: 'Einspeisung', vorhanden: null, haWert: 400 })
  })
})
