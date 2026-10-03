/**
 * W3(f) — das T-Konto-Hauptbuch führt auf das Monatsergebnis des Backends (Vorlage B6/W3, E2).
 *
 * Paket „Ergebnisgrößen Monat/Jahr in den Layer" (03.10.2026). Die Fixture ist die Monatsantwort für Juni 2025 der
 * pytest-Fixture `anlage_alle_achsen` (`backend/tests/test_ergebnis_symmetrie_monat_jahr.py`), über die echte Route
 * erzeugt und auf die Felder gekürzt, die `baueTKonto` liest: Regelbesteuerung 19 % (USt-Anteil 12,83 €), Balkonkraftwerk
 * mit Erzeugung, Erzeuger mit eigenem Satz (3,00 €), Sonstige Position (Ertrag 150 €), PV-Betriebskosten 10 €.
 *
 * Geprüft: Σ HABEN − Σ SOLL (`nettoT`, das Hauptbuch) == `ergebnis_euro`, und die USt steht als eigene SOLL-Zeile.
 *
 * Seit A2 (Entscheid Fable-Master 03.10.2026) über ALLE zwölf Monate und das Jahr derselben Fixture
 * (`src/test/w3-antworten.fixture.json`, über die echten Routen erzeugt) — für das T-Konto-Hauptbuch UND die
 * Komponenten-Tabelle (Summenzeile − Stromrechnung). Bis dahin wichen zwei Monatsformen ab: der Klemm-Monat Januar
 * (Einspeisung > Erzeugung, Eigenverbrauch 0 — die BKW-Zeile buchte trotzdem 15 €) und der Datenlücken-Monat Mai
 * (der P9-Rest `bkw_ersparnis_euro`, 12 €, fehlte). Regel: `evAufteilung.ts::bkwAufteilung`.
 *
 * Schwesterdateien: TKonto.test.tsx, TKonto.a6-herleitung.test.tsx.
 */
import { describe, it, expect } from 'vitest'
import { baueTKonto } from './TKonto'
import { komponentenFinanzSaldo } from './KomponentenFinanzTabelle'
import { aktuellerMonat } from '../../test/factories'
import type { AktuellerMonatResponse } from '../../api/aktuellerMonat'
import fixture from '../../test/w3-antworten.fixture.json'

const W3 = fixture as unknown as { monate: AktuellerMonatResponse[]; jahr: AktuellerMonatResponse }
const ALLE: Array<[string, AktuellerMonatResponse]> = [
  ...W3.monate.map((m): [string, AktuellerMonatResponse] => [`${m.jahr}-${m.monat}`, m]),
  ['Jahr 2025', W3.jahr],
]

const JUNI = aktuellerMonat(2025, 6, {
  pv_erzeugung_kwh: 1250, einspeisung_kwh: 880, netzbezug_kwh: 150, eigenverbrauch_kwh: 370,
  direktverbrauch_kwh: 370, gesamtverbrauch_kwh: 520, bkw_erzeugung_kwh: 50,
  hat_balkonkraftwerk: true, hat_sonstiges: true,
  einspeise_erloes_euro: 70.4, netzbezug_kosten_euro: 55, netzbezug_arbeitspreis_kosten_euro: 45,
  ev_ersparnis_euro: 111, netto_ertrag_euro: 321.57,
  sonstige_ertraege_euro: 150, sonstige_netto_euro: 150, anlage_sonstige_ertraege_euro: 150,
  ust_eigenverbrauch_euro: 12.83, erzeuger_erloes_euro: 3,
  ergebnis_vor_betriebskosten_euro: 266.57, ergebnis_euro: 256.57,
  netzbezug_preis_cent: 30, einspeise_preis_cent: 8, grundgebuehr_euro: 10,
  betriebskosten_anteilig_euro: 10, betriebskosten_anteilig_jahr_euro: 120, betriebskosten_anteilig_anzahl: 1,
  investitionen_financials: [
    { investition_id: 1, bezeichnung: 'Dach', typ: 'pv-module', betriebskosten_monat_euro: 10, betriebskosten_jahr_euro: 120,
      erloes_euro: null, erloes_formel: null, erloes_berechnung: null, erloes_label: 'Einspeisung', ersparnis_euro: null,
      ersparnis_label: '', formel: null, berechnung: null, sonstige_ertraege_euro: 0, sonstige_ausgaben_euro: 0 },
    { investition_id: 2, bezeichnung: 'Balkon', typ: 'balkonkraftwerk', betriebskosten_monat_euro: 0, betriebskosten_jahr_euro: 0,
      erloes_euro: null, erloes_formel: null, erloes_berechnung: null, erloes_label: 'Einspeisung', ersparnis_euro: 15,
      ersparnis_label: 'Eigenverbrauch-Ersparnis', formel: 'BKW-Eigenverbrauch × Netzbezugspreis',
      berechnung: '50,0 kWh × 30,00 ct/kWh', sonstige_ertraege_euro: 0, sonstige_ausgaben_euro: 0 },
    { investition_id: 3, bezeichnung: 'Mini-BHKW', typ: 'sonstiges', betriebskosten_monat_euro: 0, betriebskosten_jahr_euro: 0,
      erloes_euro: 3, erloes_formel: 'Am Gerät gepflegter Einspeise-Erlös (eigener Vergütungssatz) — von eedc nicht nachgerechnet',
      erloes_berechnung: null, erloes_label: 'Einspeisung', ersparnis_euro: null, ersparnis_label: '', formel: null,
      berechnung: null, sonstige_ertraege_euro: 0, sonstige_ausgaben_euro: 0 },
  ],
})

describe('W3(f) — T-Konto-Hauptbuch == Monatsergebnis (Regelbesteuerung)', () => {
  it('Σ HABEN − Σ SOLL ist das ergebnis_euro der Antwort', () => {
    const t = baueTKonto(JUNI)
    expect(t.nettoT).toBeCloseTo(JUNI.ergebnis_euro!, 2)
  })

  it('die USt auf den Eigenverbrauch steht als eigene SOLL-Zeile', () => {
    const t = baueTKonto(JUNI)
    const ust = t.sollPosten.find((p) => p.label === 'USt auf Eigenverbrauch')
    expect(ust?.wert).toBe(12.83)
  })
})

describe('W3(f) — alle zwölf Monate und das Jahr der Fixture', () => {
  it.each(ALLE)('%s: T-Konto-Hauptbuch == ergebnis_euro', (_name, d) => {
    expect(d.ergebnis_euro).not.toBeNull()
    expect(baueTKonto(d).nettoT).toBeCloseTo(d.ergebnis_euro!, 2)
  })

  it.each(ALLE)('%s: Komponenten-Tabelle − Stromrechnung == ergebnis_euro', (_name, d) => {
    expect(komponentenFinanzSaldo(d) - (d.netzbezug_kosten_euro ?? 0)).toBeCloseTo(d.ergebnis_euro!, 2)
  })

  it('Klemm-Monat Januar: keine BKW-Zeile, wo kein Eigenverbrauch ist', () => {
    const jan = W3.monate[0]
    expect(jan.ev_ersparnis_euro).toBe(0)
    expect(baueTKonto(jan).habenPosten.some((p) => p.label.startsWith('Balkon'))).toBe(false)
  })

  it('Datenlücken-Monat Mai: der P9-Rest steht als eigene Zeile, die PV-Zeile behält die volle Ersparnis', () => {
    const mai = W3.monate[4]
    const t = baueTKonto(mai)
    expect(t.habenPosten.find((p) => p.label.startsWith('BKW-Ersparnis'))?.wert).toBe(12)
    expect(t.habenPosten.find((p) => p.label === 'PV-Eigenverbrauch-Ersparnis')?.wert).toBeCloseTo(mai.ev_ersparnis_euro!, 2)
  })
})
