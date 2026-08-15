/**
 * `monatBilanzParkIds` — die Liste muss decken, was wirklich gerendert wird.
 *
 * Der Bilanz-Block verschwindet erst, wenn **alle** seine Teil-Anzeigen geparkt
 * sind (`alleGeparkt`). Steht in der Liste eine ID, die keine Anzeige hat,
 * lässt sich der Block nie ganz parken; fehlt eine, verschwindet er zu früh.
 * Beides ist von außen nur schwer zu sehen — deshalb diese Probe.
 *
 * Anlass: die Monatsprognose-Kachel (dietmar1968, T89667 #155) wird **nur** in
 * `MonatBilanz` gerendert, während sich Monat und Jahr diese Funktion teilen.
 */
import { describe, it, expect } from 'vitest'
import { monatBilanzParkIds } from './bilanzParkIds'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'

const d = (over: Partial<AktuellerMonatResponse> = {}): AktuellerMonatResponse => ({
  pv_erzeugung_kwh: 264.75, eigenverbrauch_kwh: null, einspeisung_kwh: null,
  soll_pv_kwh: 179.1, soll_pv_kwh_monat: 1387.9,
  soll_pv_tage: 4, soll_pv_tage_gesamt: 31,
  ...over,
} as AktuellerMonatResponse)

describe('monatBilanzParkIds', () => {
  it('führt die Monatsprognose im Monat, aber nicht im Jahr', () => {
    expect(monatBilanzParkIds(d())).toContain('el:bilanz-monatsprognose')
    // Das Jahr rendert die Kachel nicht — stünde die ID trotzdem in der Liste,
    // wartete der Jahres-Block auf das Parken eines Elements, das es nicht gibt.
    expect(monatBilanzParkIds(d(), 'jahr')).not.toContain('el:bilanz-monatsprognose')
  })

  it('lässt sie weg, wo die Kachel selbst schweigt (abgeschlossener Monat)', () => {
    const fertig = d({
      soll_pv_kwh: 1509, soll_pv_kwh_monat: 1509, soll_pv_tage: 31, soll_pv_tage_gesamt: 31,
    })
    expect(monatBilanzParkIds(fertig)).not.toContain('el:bilanz-monatsprognose')
  })

  it('trägt die Bestandsanzeigen unverändert', () => {
    expect(monatBilanzParkIds(d())).toEqual(expect.arrayContaining([
      'el:bilanz-vergleich', 'el:bilanz-grundlast',
    ]))
    // PV-Verteilung nur mit den Mengen dahinter (Gate wortgleich in MonatBilanz).
    expect(monatBilanzParkIds(d())).not.toContain('el:bilanz-verteilung')
    expect(monatBilanzParkIds(d({ eigenverbrauch_kwh: 100, einspeisung_kwh: 50 })))
      .toContain('el:bilanz-verteilung')
  })
})
