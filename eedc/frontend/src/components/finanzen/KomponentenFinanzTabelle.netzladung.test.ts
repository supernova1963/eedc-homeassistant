/**
 * N-606 — die Netzladung des Speichers zählt in der Komponenten-Tabelle einmal: in der Stromrechnung.
 *
 * Bis 03.10.2026 buchte `zeilenAus` die Netzladungs-Kosten als Aufwand der Speicher-Zeile („stecken NICHT im
 * Haus-Netzbezug"), während das T-Konto (R15-5b) sie richtig als Teil der Stromrechnung (Hauszähler) ausweist; die
 * Haushaltsperspektive zog danach die volle Stromrechnung ab — doppelt. Gemessen an r28 + r27: 30 Monate, Σ 290,10 €.
 *
 * Fixture: Einspeisung 50 €, Eigenverbrauchs-Ersparnis 100 € (davon 10 € Speicher-Zeile), Stromrechnung 100 € inkl.
 * 20 € Netzladung ⇒ Monatsergebnis 50 €. Die Tabelle muss mit „Saldo − Stromrechnung" dort ankommen, wie das T-Konto.
 *
 * Schwesterdateien: TKonto.w3f.test.ts (Hauptbuch == Ergebnis über die W3-Fixture), evAufteilung.test.tsx.
 */
import { describe, it, expect } from 'vitest'
import { komponentenFinanzSaldo } from './KomponentenFinanzTabelle'
import { baueTKonto } from './TKonto'
import { aktuellerMonat } from '../../test/factories'

const D = aktuellerMonat(2025, 3, {
  einspeise_erloes_euro: 50, ev_ersparnis_euro: 100, netzbezug_kosten_euro: 100,
  speicher_ladung_netz_kosten_euro: 20, speicher_ladung_netz_kwh: 66.7,
  netto_ertrag_euro: 150, ergebnis_vor_betriebskosten_euro: 50, ergebnis_euro: 50,
  investitionen_financials: [
    { investition_id: 1, bezeichnung: 'Akku', typ: 'speicher', betriebskosten_monat_euro: 0, betriebskosten_jahr_euro: 0,
      erloes_euro: null, erloes_formel: null, erloes_berechnung: null, erloes_label: 'Einspeisung', ersparnis_euro: 10,
      ersparnis_label: 'Ersparnis (Spread)', formel: null, berechnung: null, sonstige_ertraege_euro: 0,
      sonstige_ausgaben_euro: 0 },
  ],
})

describe('N-606 — Netzladung nur in der Stromrechnung', () => {
  it('Komponenten-Saldo − Stromrechnung == Monatsergebnis (wie das T-Konto)', () => {
    expect(komponentenFinanzSaldo(D) - D.netzbezug_kosten_euro!).toBeCloseTo(D.ergebnis_euro!, 2)
    expect(baueTKonto(D).nettoT).toBeCloseTo(D.ergebnis_euro!, 2)
  })
})
