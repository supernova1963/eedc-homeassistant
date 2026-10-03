import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TKonto } from './TKonto'
import { aktuellerMonat } from '../../test/factories'
import type { AktuellerMonatResponse } from '../../api/aktuellerMonat'

/**
 * A6 — die drei Geldzeilen des T-Kontos nennen ihre eingesetzten Werte (N-365).
 *
 * ## Was vorher stand
 *
 * · **Erlös-Zeile (BKW):** Formel UND Zahlen in EINEM Satz, beides unter der
 *   Überschrift „Formel" — „Einspeisung × Einspeisevergütung — 123,4 kWh ×
 *   8,20 ct/kWh". An jeder anderen Kachel stehen sie getrennt.
 * · **Betriebskosten je Gerät:** „Betriebskosten/Jahr ÷ 12" — der Jahresbetrag
 *   stand auf keiner Fläche.
 * · **Betriebskosten (anteilig):** „Σ (…) aller aktiven Investitionen" — und
 *   diese Zeile erscheint GENAU DANN, wenn es keine Gerätezeilen gibt, der
 *   Anwender sieht die Summanden also nirgends sonst.
 *
 * ## Warum die Werte aus dem Backend kommen
 *
 * Der Client teilt nicht selbst. `betriebskosten_jahr_euro` wird im selben
 * Builder gesetzt wie `betriebskosten_monat_euro` — würde der Client
 * `monat × 12` bilden, stünde im Jahres-T-Konto (wo der Betrag daneben die Σ
 * über zwölf Monate ist) eine Rechnung, die auf eine andere Zahl führt.
 * rilmor-mhrs (#402) ist genau an diesen Zeilen hängengeblieben.
 *
 * ⚠ Der `FormelTooltip` baut seinen Inhalt erst bei `mouseEnter`. Im T-Konto
 * umschließt er das **Label** der Zeile (`TKonto.tsx`: `<FormelTooltip …>
 * {item.label}</FormelTooltip>`) — anders als in `KPICard`, wo er um den WERT
 * liegt. Am DOM gemessen, nicht geraten: eine Probe, die auf den Betrag
 * `mouseEnter`t, öffnet gar nichts (erste Fassung tat genau das).
 */
const basis = aktuellerMonat(2025, 5, {
  anlage_name: 'Demo',
  einspeisung_kwh: 100, einspeise_preis_cent: 8, einspeise_erloes_euro: 8,
  eigenverbrauch_kwh: 120, ev_ersparnis_euro: 36,
  netzbezug_kwh: 50, netzbezug_preis_cent: 30, netzbezug_kosten_euro: 15,
  netto_ertrag_euro: 29,
})

/** Rendert das T-Konto und öffnet den Tooltip am Label dieser Zeile. */
function zeigeTooltip(d: AktuellerMonatResponse, label: RegExp) {
  render(<TKonto d={d} />)
  const treffer = screen.getAllByText(label)
  expect(treffer.length, `Zeile ${label} muss es geben`).toBeGreaterThan(0)
  fireEvent.mouseEnter(treffer[0])
}

const mitBkw = (over: Record<string, unknown> = {}) => ({
  ...basis,
  investitionen_financials: [{
    investition_id: 3, bezeichnung: 'BKW Süd', typ: 'balkonkraftwerk',
    betriebskosten_monat_euro: 0, betriebskosten_jahr_euro: 0,
    erloes_euro: 10.12, ersparnis_euro: null, ersparnis_label: '',
    formel: null, berechnung: null,
    erloes_formel: 'Einspeisung × Einspeisevergütung',
    erloes_berechnung: '123,4 kWh × 8,20 ct/kWh',
    erloes_label: 'Einspeisung',
    sonstige_ertraege_euro: 0, sonstige_ausgaben_euro: 0,
    ...over,
  }],
})

describe('A6 — T-Konto Erlös-Zeile', () => {
  it('trennt Formel und eingesetzte Werte', () => {
    zeigeTooltip(mitBkw(), /^BKW Süd — Einspeisung$/)
    expect(screen.getAllByText('Einspeisung × Einspeisevergütung').length).toBeGreaterThan(0)
    expect(screen.getAllByText('123,4 kWh × 8,20 ct/kWh').length).toBeGreaterThan(0)
  })

  it('eine gepflegte Erlös-Zeile bleibt ohne Rechnung', () => {
    // Gegenprobe und zugleich die zweite Regelhälfte: bei einem gepflegten
    // Betrag gibt es keine Rechnung, die man zeigen könnte — dort steht eine
    // Herkunftsangabe. Ohne diese Probe wäre die erste auch dann grün, wenn
    // der Client irgendetwas in den Berechnungs-Slot schriebe.
    zeigeTooltip(mitBkw({
      erloes_formel: 'Am Gerät gepflegter Einspeise-Erlös (eigener Vergütungssatz) — von eedc nicht nachgerechnet',
      erloes_berechnung: null,
    }), /^BKW Süd — Einspeisung$/)
    expect(screen.getAllByText(/Am Gerät gepflegter Einspeise-Erlös/).length).toBeGreaterThan(0)
    expect(screen.queryByText('123,4 kWh × 8,20 ct/kWh')).toBeNull()
  })
})

describe('A6 — T-Konto Betriebskosten', () => {
  it('die Gerätezeile nennt den Jahresbetrag, aus dem der Zwölftel entsteht', () => {
    zeigeTooltip({
      ...basis,
      investitionen_financials: [{
        investition_id: 4, bezeichnung: 'Wärmepumpe', typ: 'waermepumpe',
        betriebskosten_monat_euro: 12.5, betriebskosten_jahr_euro: 150,
        erloes_euro: null, ersparnis_euro: null, ersparnis_label: '',
        formel: null, berechnung: null, erloes_formel: null,
        sonstige_ertraege_euro: 0, sonstige_ausgaben_euro: 0,
      }],
    }, /^Wärmepumpe — Betriebskosten$/)
    expect(screen.getAllByText('Betriebskosten/Jahr ÷ 12').length).toBeGreaterThan(0)
    expect(screen.getAllByText('150,00 €/Jahr ÷ 12').length).toBeGreaterThan(0)
  })

  it('ohne gelieferten Jahresbetrag bleibt die Rechnung weg (Jahres-T-Konto)', () => {
    // Im Jahres-Aggregat ist der Betrag daneben die Σ über zwölf Monate;
    // „X €/Jahr ÷ 12" führte dort auf eine andere Zahl. Die Jahresfaltung (Backend `falte_zeitraum`) leert
    // das Feld deshalb — hier wird geprüft, dass der Client das respektiert
    // statt selbst `monat × 12` zu bilden.
    zeigeTooltip({
      ...basis,
      investitionen_financials: [{
        investition_id: 4, bezeichnung: 'Wärmepumpe', typ: 'waermepumpe',
        betriebskosten_monat_euro: 150, betriebskosten_jahr_euro: undefined,
        erloes_euro: null, ersparnis_euro: null, ersparnis_label: '',
        formel: null, berechnung: null, erloes_formel: null,
        sonstige_ertraege_euro: 0, sonstige_ausgaben_euro: 0,
      }],
    }, /^Wärmepumpe — Betriebskosten$/)
    expect(screen.getAllByText('Betriebskosten/Jahr ÷ 12').length).toBeGreaterThan(0)
    expect(screen.queryByText(/€\/Jahr ÷ 12/)).toBeNull()
  })

  it('die anteilige Zeile nennt Σ Jahresbeträge und die Anzahl der Geräte', () => {
    // Diese Zeile existiert nur ohne Per-Investition-Zeilen (`hasPerInv === false`).
    zeigeTooltip({
      ...basis,
      investitionen_financials: [],
      betriebskosten_anteilig_euro: 41.67,
      betriebskosten_anteilig_jahr_euro: 500,
      betriebskosten_anteilig_anzahl: 3,
    }, /^Betriebskosten \(anteilig\)$/)
    expect(screen.getAllByText('Σ (Betriebskosten/Jahr ÷ 12) aller aktiven Investitionen').length).toBeGreaterThan(0)
    expect(screen.getAllByText('500,00 €/Jahr ÷ 12 (3 Investitionen)').length).toBeGreaterThan(0)
  })

  it('im Jahr heißt die Formel „Σ der Monats-Zwölftel" statt „÷ 12"', () => {
    // V-WK04-6: Dasselbe T-Konto trägt Monat UND Jahr. Im Jahr ist der Betrag
    // daneben die Σ über zwölf Monatszwölftel — „Betriebskosten/Jahr ÷ 12"
    // beschreibt dort eine andere Rechnung als die Zahl. Marke ist `monat: 0`
    // (die Kennzeichnung der Jahresfaltung, seit 03.10.2026 Backend `falte_zeitraum`).
    zeigeTooltip({
      ...basis, monat: 0, monat_name: '2025',
      investitionen_financials: [{
        investition_id: 4, bezeichnung: 'Wärmepumpe', typ: 'waermepumpe',
        betriebskosten_monat_euro: 150, betriebskosten_jahr_euro: undefined,
        erloes_euro: null, ersparnis_euro: null, ersparnis_label: '',
        formel: null, berechnung: null, erloes_formel: null,
        sonstige_ertraege_euro: 0, sonstige_ausgaben_euro: 0,
      }],
    }, /^Wärmepumpe — Betriebskosten$/)
    expect(screen.getAllByText('Σ der Monats-Zwölftel (Betriebskosten/Jahr ÷ 12)').length).toBeGreaterThan(0)
    expect(screen.queryByText('Betriebskosten/Jahr ÷ 12')).toBeNull()
  })

  it('im Monat bleibt es bei „Betriebskosten/Jahr ÷ 12"', () => {
    // Die Gegenprobe. Ohne sie wäre die Regel oben auch dann erfüllt, wenn
    // jemand die Jahres-Formel pauschal überall hinschriebe.
    zeigeTooltip({
      ...basis,
      investitionen_financials: [{
        investition_id: 4, bezeichnung: 'Wärmepumpe', typ: 'waermepumpe',
        betriebskosten_monat_euro: 12.5, betriebskosten_jahr_euro: 150,
        erloes_euro: null, ersparnis_euro: null, ersparnis_label: '',
        formel: null, berechnung: null, erloes_formel: null,
        sonstige_ertraege_euro: 0, sonstige_ausgaben_euro: 0,
      }],
    }, /^Wärmepumpe — Betriebskosten$/)
    expect(screen.getAllByText('Betriebskosten/Jahr ÷ 12').length).toBeGreaterThan(0)
    expect(screen.queryByText(/Σ der Monats-Zwölftel/)).toBeNull()
  })

  it('auch die anteilige Zeile benennt im Jahr die Σ der Zwölftel', () => {
    zeigeTooltip({
      ...basis, monat: 0, monat_name: '2025',
      investitionen_financials: [],
      betriebskosten_anteilig_euro: 500,
    }, /^Betriebskosten \(anteilig\)$/)
    expect(screen.getAllByText('Σ der Monats-Zwölftel aller aktiven Investitionen').length).toBeGreaterThan(0)
    expect(screen.queryByText('Σ (Betriebskosten/Jahr ÷ 12) aller aktiven Investitionen')).toBeNull()
  })

  it('bei genau einer Investition heißt es „Investition"', () => {
    zeigeTooltip({
      ...basis,
      investitionen_financials: [],
      betriebskosten_anteilig_euro: 12.5,
      betriebskosten_anteilig_jahr_euro: 150,
      betriebskosten_anteilig_anzahl: 1,
    }, /^Betriebskosten \(anteilig\)$/)
    expect(screen.getAllByText('150,00 €/Jahr ÷ 12 (1 Investition)').length).toBeGreaterThan(0)
  })
})
