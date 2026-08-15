/**
 * `createMonatsZeitreihe` — die Zeitreihe hinter „Auswertungen → Finanzen" und
 * der Werte-Tabelle.
 *
 * **Seit N-22 (2026-08-04) rechnet sie keine Finanzen mehr.** Die §51-Tests, die
 * hier standen, prüften eine zweite Finanz-Engine im Client — mit eigenem
 * Tarif-Stichtag, eigenem §51-Abzug und ohne USt/BKW-Regel. Der SoT liegt im
 * Backend (`services/finanz_zeilen.py` + `core/berechnungen/finanz_aggregat.py`,
 * belegt in `test_monatsdaten_aggregiert_finanzen.py`); hier wird nur noch
 * geprüft, dass die Zeile die gelieferten Werte **durchreicht statt zu rechnen**.
 */
import { describe, it, expect } from 'vitest'
import { createMonatsZeitreihe } from './types'
import type { AggregierteMonatsdaten } from '../../api/monatsdaten'

const md = (over: Partial<AggregierteMonatsdaten> = {}): AggregierteMonatsdaten => ({
  id: 1, anlage_id: 1, jahr: 2026, monat: 5,
  einspeisung_kwh: 1000, netzbezug_kwh: 200,
  globalstrahlung_kwh_m2: null, sonnenstunden: null,
  pv_erzeugung_kwh: 1500, pv_module_kwh: 1500, bkw_kwh: null, sonstige_erzeugung_kwh: null, sonstige_verbrauch_kwh: null,
  erzeugung_hinter_zaehler_kwh: 1500,
  speicher_ladung_kwh: null, speicher_entladung_kwh: null, speicher_netzladung_kwh: null,
  wp_strom_kwh: null, wp_strom_heizen_kwh: null, wp_strom_warmwasser_kwh: null,
  wp_heizung_kwh: null, wp_warmwasser_kwh: null,
  eauto_ladung_kwh: null, eauto_km: null,
  wallbox_ladung_kwh: null, wallbox_ladung_pv_kwh: null,
  direktverbrauch_kwh: 500, eigenverbrauch_kwh: 500, gesamtverbrauch_kwh: 700,
  autarkie_prozent: 71.4, eigenverbrauchsquote_prozent: 33.3,
  einspeisung_neg_preis_kwh: null,
  einspeise_erloes_euro: 82, einspeise_nicht_verguetet_euro: 0,
  ev_ersparnis_euro: 150, bkw_ersparnis_euro: 0, ust_eigenverbrauch_euro: 0,
  netzbezug_kosten_euro: 60, netto_ertrag_euro: 232, netto_bilanz_euro: 172,
  netzbezug_preis_cent: 30,
  hat_legacy_daten: false,
  ...over,
})

describe('createMonatsZeitreihe — Finanzen kommen aus dem Backend (N-22)', () => {
  it('reicht Erlös, Ersparnis, Kosten und Netto durch, ohne sie neu zu rechnen', () => {
    // Die gelieferten Zahlen sind absichtlich NICHT die, die die alte
    // Client-Formel aus denselben Mengen gerechnet hätte (1000 kWh × 8,2 ct =
    // 82 € Erlös, 500 kWh × 30 ct = 150 € EV). Hier stehen bewusst andere
    // Werte: wer wieder rechnet statt zu lesen, fällt auf.
    const [z] = createMonatsZeitreihe([md({
      einspeise_erloes_euro: 71.5, ev_ersparnis_euro: 133.25,
      netzbezug_kosten_euro: 74, netto_ertrag_euro: 204.75, netto_bilanz_euro: 130.75,
    })])
    expect(z.einspeise_erloes).toBe(71.5)
    expect(z.ev_ersparnis).toBe(133.25)
    expect(z.netzbezug_kosten).toBe(74)
    expect(z.netto_ertrag).toBe(204.75)
    expect(z.netto_bilanz).toBe(130.75)
  })

  it('zählt die BKW-Ersparnis zur EV-Ersparnis (P9-Ersatzträger)', () => {
    // Ein BKW-Monat ohne erfasste Erzeugung trägt seinen gemessenen
    // Eigenverbrauch separat — in der Spalte „EV-Ersparnis" gehört er dazu,
    // sonst summiert die Spalte auf weniger als der Netto-Ertrag daneben.
    const [z] = createMonatsZeitreihe([md({ ev_ersparnis_euro: 100, bkw_ersparnis_euro: 12.5 })])
    expect(z.ev_ersparnis).toBe(112.5)
  })

  it('führt die USt auf Eigenverbrauch als eigene Größe (sie steckt im Netto)', () => {
    const [z] = createMonatsZeitreihe([md({ ust_eigenverbrauch_euro: 41.3, netto_ertrag_euro: 190.7 })])
    expect(z.ust_eigenverbrauch).toBe(41.3)
    expect(z.netto_ertrag).toBe(190.7)
  })

  it('übernimmt den effektiven Monatspreis, statt ihn aus einem Tarif zu suchen', () => {
    // Flex-Ø 24,8 ct schlägt den Stammpreis — die Auflösung (P8) liegt im
    // Backend, der Client kennt weder Tarif-Historie noch Stichtag mehr.
    const [z] = createMonatsZeitreihe([md({ netzbezug_preis_cent: 24.8 })])
    expect(z.netzbezug_preis_cent).toBe(24.8)
  })

  it('reicht den §51-Abzug als Diagnose durch', () => {
    const [z] = createMonatsZeitreihe([md({
      einspeisung_neg_preis_kwh: 120, einspeise_nicht_verguetet_euro: 9.84,
      einspeise_erloes_euro: 72.16,
    })])
    expect(z.einspeise_erloes).toBe(72.16)
    expect(z.einspeise_nicht_verguetet_euro).toBe(9.84)
    expect(z.einspeise_neg_preis_kwh).toBe(120)
  })

  it('behandelt eine gemessene 0 als Wert, nicht als Lücke', () => {
    // `||` statt `??` ließ einen Monat mit 0 kWh Erzeugung auf den
    // Ersatzausdruck durchfallen (Teil von N-22).
    const [z] = createMonatsZeitreihe([md({
      pv_erzeugung_kwh: 0, eigenverbrauch_kwh: 0, gesamtverbrauch_kwh: 0, netzbezug_kwh: 200,
    })])
    expect(z.erzeugung).toBe(0)
    expect(z.gesamtverbrauch).toBe(0)
  })
})

/**
 * N-21 — CO₂ wird nachgeschlagen, nicht gerechnet.
 *
 * Beide Tests fallen gegen den Stand vor N-21: dort stand
 * `erzeugung × CO2_FAKTOR_KG_KWH`, also 1.500 kWh × 0,38 = **570 kg** —
 * unabhängig davon, ob eine kanonische Reihe mitgegeben wurde oder nicht.
 */
describe('createMonatsZeitreihe — CO₂ kommt aus dem Kanon (N-21)', () => {
  const co2 = (over = {}) => ({
    jahr: 2026, monat: 5, monat_name: 'Mai',
    co2_pv_kg: 190, co2_wp_kg: 60, co2_emob_kg: 40,
    co2_gesamt_kg: 290, co2_kumuliert_kg: 290, autarkie_prozent: 71.4,
    ...over,
  })

  it('übernimmt den PV-Anteil des passenden Monats — nicht Erzeugung × 0,38', () => {
    const [z] = createMonatsZeitreihe([md()], undefined, [co2()])
    // Eigenverbrauch 500 kWh × 0,38 = 190 kg, vom Backend geliefert.
    expect(z.co2_einsparung).toBe(190)
    // Gegenprobe auf den alten Wert: 1.500 kWh Erzeugung × 0,38 = 570 kg,
    // also das Dreifache — die eingespeisten 1.000 kWh waren mitgezählt.
    expect(z.co2_einsparung).not.toBe(570)
  })

  it('ohne kanonische Reihe bleibt die Spalte leer, statt genähert zu werden', () => {
    // „Kein Wert" ist eine ehrliche Aussage; eine still danebengerechnete Zahl
    // neben der kanonischen wäre genau die Drift, die N-21 beendet hat.
    expect(createMonatsZeitreihe([md()])[0].co2_einsparung).toBeNull()
    // Auch ein Monat, den die Reihe nicht kennt, bleibt leer (kein Fallback).
    expect(createMonatsZeitreihe([md({ monat: 7 })], undefined, [co2()])[0].co2_einsparung).toBeNull()
  })
})

describe('Sonstiges-Spalten (Melder rapahl, 2026-08-14)', () => {
  it('reicht beide Richtungen durch und macht aus „kein Gerät" keine 0', () => {
    const [zeile] = createMonatsZeitreihe([
      md({ sonstige_erzeugung_kwh: 300, sonstige_verbrauch_kwh: 45 }),
    ])
    expect(zeile.sonstiges_erzeugung).toBe(300)
    expect(zeile.sonstiges_verbrauch).toBe(45)

    const [ohne] = createMonatsZeitreihe([md()])
    expect(ohne.sonstiges_erzeugung).toBeNull()
    expect(ohne.sonstiges_verbrauch).toBeNull()
  })
})
