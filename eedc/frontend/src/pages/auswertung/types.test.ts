/**
 * `createMonatsZeitreihe` — die Finanz-Formeln der Auswertungen.
 *
 * Diese Zeitreihe speist sowohl die v4-Seite „Auswertungen → Finanzen" als auch
 * die Werte-Tabelle. Sie rechnet im Frontend, muss aber dieselben Ergebnisse
 * liefern wie der Backend-SoT (`core/berechnungen/finanz_aggregat.py`) — sonst
 * stehen auf einer Seite zwei verschiedene Einspeiseerlöse (Block „Finanz-
 * Übersicht" gegen „SOLL/HABEN-T-Konto").
 */
import { describe, it, expect } from 'vitest'
import { createMonatsZeitreihe } from './types'
import type { AggregierteMonatsdaten } from '../../api/monatsdaten'
import type { Strompreis } from '../../types'

const md = (over: Partial<AggregierteMonatsdaten> = {}): AggregierteMonatsdaten => ({
  id: 1, anlage_id: 1, jahr: 2026, monat: 5,
  einspeisung_kwh: 1000, netzbezug_kwh: 200,
  globalstrahlung_kwh_m2: null, sonnenstunden: null,
  pv_erzeugung_kwh: 1500, pv_anlage_kwh: 1500, bkw_kwh: null, sonstige_erzeugung_kwh: null,
  speicher_ladung_kwh: null, speicher_entladung_kwh: null, speicher_netzladung_kwh: null,
  wp_strom_kwh: null, wp_strom_heizen_kwh: null, wp_strom_warmwasser_kwh: null,
  wp_heizung_kwh: null, wp_warmwasser_kwh: null,
  eauto_ladung_kwh: null, eauto_km: null,
  wallbox_ladung_kwh: null, wallbox_ladung_pv_kwh: null,
  direktverbrauch_kwh: 500, eigenverbrauch_kwh: 500, gesamtverbrauch_kwh: 700,
  autarkie_prozent: 71.4, eigenverbrauchsquote_prozent: 33.3,
  einspeisung_neg_preis_kwh: null,
  hat_legacy_daten: false,
  ...over,
})

const tarif = (over: Partial<Strompreis> = {}): Strompreis => ({
  id: 1, anlage_id: 1,
  netzbezug_arbeitspreis_cent_kwh: 30,
  einspeiseverguetung_cent_kwh: 8.2,
  gueltig_ab: '2020-01-01',
  verwendung: 'standard',
  ...over,
} as Strompreis)

describe('createMonatsZeitreihe — §51 EEG', () => {
  it('ohne §51-Daten (null) bleibt der Erlös ungekürzt', () => {
    const [z] = createMonatsZeitreihe([md()], undefined, tarif())
    expect(z.einspeise_erloes).toBeCloseTo(82.0, 6)
    expect(z.einspeise_nicht_verguetet_euro).toBe(0)
  })

  it('zieht §51-kWh ab; Netto-Ertrag und Netto-Bilanz ziehen mit', () => {
    const [z] = createMonatsZeitreihe([md({ einspeisung_neg_preis_kwh: 120 })], undefined, tarif())
    expect(z.einspeise_erloes).toBeCloseTo((1000 - 120) * 8.2 / 100, 6)
    expect(z.einspeise_nicht_verguetet_euro).toBeCloseTo(120 * 8.2 / 100, 6)
    // netto_ertrag = Einspeiseerlös + EV-Ersparnis (500 kWh × 30 ct = 150 €)
    expect(z.netto_ertrag).toBeCloseTo((1000 - 120) * 8.2 / 100 + 150, 6)
    // netto_bilanz zusätzlich abzüglich Netzbezug-Kosten (200 kWh × 30 ct = 60 €)
    expect(z.netto_bilanz).toBeCloseTo(z.netto_ertrag - 60, 6)
  })

  it('nutzt je Monat den historisch gültigen Tarif — auch beim §51-Abzug', () => {
    const tarife = [
      tarif({ id: 1, einspeiseverguetung_cent_kwh: 8.2, gueltig_ab: '2020-01-01', gueltig_bis: '2026-03-31' }),
      tarif({ id: 2, einspeiseverguetung_cent_kwh: 7.0, gueltig_ab: '2026-04-01' }),
    ]
    const reihe = createMonatsZeitreihe([
      md({ monat: 2, einspeisung_neg_preis_kwh: 100 }),
      md({ monat: 6, einspeisung_neg_preis_kwh: 100 }),
    ], undefined, tarife[0], tarife)
    expect(reihe[0].einspeise_erloes).toBeCloseTo(900 * 8.2 / 100, 6)
    expect(reihe[1].einspeise_erloes).toBeCloseTo(900 * 7.0 / 100, 6)
  })

  it('ohne Tarif bleibt der Erlös 0 (kein Preis, keine Rechnung)', () => {
    const [z] = createMonatsZeitreihe([md({ einspeisung_neg_preis_kwh: 120 })])
    expect(z.einspeise_erloes).toBe(0)
    expect(z.einspeise_nicht_verguetet_euro).toBe(0)
  })
})
