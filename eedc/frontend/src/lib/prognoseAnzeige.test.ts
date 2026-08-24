/**
 * Der EINE Zugriffsweg auf Prognose-Anzeigewerte — bis E6 ohne Test (M9).
 *
 * Anlass des Moduls war Rainers Befund (PN „Nachtrag", 2026-07-25): derselbe
 * Tag stand auf einer Seite mit **13 kWh** (OpenMeteo roh) und **10,8 kWh**
 * (eedc-korrigiert). Seither liefert die Antwort beide Werte, und dieses Modul
 * entscheidet, welcher angezeigt wird.
 *
 * **Die Regel, die hier festgehalten wird:** der korrigierte Wert gewinnt,
 * der Rohwert ist der Rückfall — und eine gemessene **0** ist ein korrigierter
 * Wert, kein fehlender. Fiele sie durch (`||` statt `??`), zeigte die Anzeige
 * für einen Nebeltag die unkorrigierte Rohprognose.
 */
import { describe, it, expect } from 'vitest'
import {
  prognoseDurchschnittKwh,
  prognoseQuelle,
  prognoseQuelleLabel,
  prognoseSummeKwh,
  pvErtragKwh,
  pvNachmittagKwh,
  pvVormittagKwh,
} from './prognoseAnzeige'
import type { SolarPrognose, SolarPrognoseTag } from '../api/wetter'

const tag = (over: Partial<SolarPrognoseTag> = {}): SolarPrognoseTag =>
  ({ datum: '2026-06-01', pv_ertrag_kwh: 13, ...over }) as SolarPrognoseTag

const prognose = (over: Partial<SolarPrognose> = {}): SolarPrognose =>
  ({ summe_kwh: 130, durchschnitt_kwh_tag: 13, tage: [], ...over }) as SolarPrognose

describe('pvErtragKwh', () => {
  it('zeigt den eedc-korrigierten Wert, wenn er vorliegt', () => {
    expect(pvErtragKwh(tag({ eedc_kwh: 10.8 }))).toBe(10.8)
  })

  it('faellt auf die OpenMeteo-Rohprognose zurueck', () => {
    expect(pvErtragKwh(tag())).toBe(13)
  })

  it('eine korrigierte NULL gewinnt ebenfalls', () => {
    // `||` statt `??` liesse hier die 13 durch — genau Rainers Befund.
    expect(pvErtragKwh(tag({ eedc_kwh: 0 }))).toBe(0)
  })
})

describe('Vormittags-/Nachmittags-Anteil', () => {
  it('folgen dem korrigierten Wert, wenn beide Haelften korrigiert sind', () => {
    const t = tag({
      eedc_kwh: 10.8, eedc_morgens_kwh: 4, eedc_nachmittags_kwh: 6.8,
      pv_ertrag_morgens_kwh: 5, pv_ertrag_nachmittags_kwh: 8,
    })
    expect(pvVormittagKwh(t)).toBe(4)
    expect(pvNachmittagKwh(t)).toBe(6.8)
  })

  it('bleiben beim Rohwert, wenn der korrigierte Split fehlt', () => {
    // Sonst stuenden korrigierte Summe und rohe Haelften nebeneinander —
    // dieselbe Klasse „zwei Zahlen auf einer Seite", nur eine Ebene tiefer.
    const t = tag({ eedc_kwh: 10.8, pv_ertrag_morgens_kwh: 5, pv_ertrag_nachmittags_kwh: 8 })
    expect(pvVormittagKwh(t)).toBe(5)
    expect(pvNachmittagKwh(t)).toBe(8)
  })

  it('sind undefined, wenn es gar keinen Split gibt', () => {
    expect(pvVormittagKwh(tag())).toBeUndefined()
    expect(pvNachmittagKwh(tag())).toBeUndefined()
  })

  it('eine korrigierte Haelfte von 0 gewinnt', () => {
    const t = tag({ eedc_kwh: 6.8, eedc_morgens_kwh: 0, pv_ertrag_morgens_kwh: 5 })
    expect(pvVormittagKwh(t)).toBe(0)
  })
})

describe('Summe und Durchschnitt', () => {
  it('nehmen die korrigierten Aggregate, wenn vorhanden', () => {
    const p = prognose({ eedc_summe_kwh: 108, eedc_durchschnitt_kwh_tag: 10.8 })
    expect(prognoseSummeKwh(p)).toBe(108)
    expect(prognoseDurchschnittKwh(p)).toBe(10.8)
  })

  it('fallen auf die rohen Aggregate zurueck', () => {
    expect(prognoseSummeKwh(prognose())).toBe(130)
    expect(prognoseDurchschnittKwh(prognose())).toBe(13)
  })

  it('eine korrigierte Summe von 0 gewinnt', () => {
    expect(prognoseSummeKwh(prognose({ eedc_summe_kwh: 0 }))).toBe(0)
  })
})

describe('Quelle', () => {
  it('nennt die vom Backend ausgewiesene Quelle', () => {
    expect(prognoseQuelle(prognose({ anzeige_quelle: 'eedc' }))).toBe('eedc')
  })

  it('faellt auf openmeteo zurueck, wenn das Feld fehlt', () => {
    expect(prognoseQuelle(prognose())).toBe('openmeteo')
  })

  it('das Label passt zur Quelle — Beschriftung und Zahl gehoeren zusammen', () => {
    expect(prognoseQuelleLabel(prognose({ anzeige_quelle: 'eedc' })))
      .not.toBe(prognoseQuelleLabel(prognose({ anzeige_quelle: 'openmeteo' })))
    expect(prognoseQuelleLabel(prognose())).toBeTruthy()
  })
})
