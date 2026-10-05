/**
 * N-633 — dienstliche Ladekosten als Posten im T-Konto und in der Komponenten-Finanztabelle (05.10.2026).
 *
 * Fixture `src/test/n633-dienstwagen.fixture.json`: Monats- und Jahresantwort (Juni 2026) der pytest-Anlage
 * `backend/tests/test_n633_sieben_sichten_eine_zahl.py::_anlage` über die echten Routen erzeugt (Cockpit → Monat,
 * Kopf von Cockpit → Jahr): Dienstwagen 200 kWh PV + 100 kWh Netz ⇒ Posten 78,00 €, Netto-Ertrag 134,00 €,
 * Ergebnis 44,00 €.
 *
 * Geprüft: Hauptbuch == `ergebnis_euro` (die Regel aus `TKonto.w3f.test.ts`), Komponenten-Saldo − Stromrechnung ==
 * `ergebnis_euro`, die Zeile heißt „Dienstliche Ladekosten" und trägt den freigegebenen Hinweis, und ohne Posten
 * gibt es die Zeile nicht.
 */
import { describe, it, expect } from 'vitest'
import { baueTKonto } from './TKonto'
import { komponentenFinanzSaldo } from './KomponentenFinanzTabelle'
import { DIENSTLICHE_LADEKOSTEN_HINWEIS } from './dienstlicheLadekosten'
import type { AktuellerMonatResponse } from '../../api/aktuellerMonat'
import fixture from '../../test/n633-dienstwagen.fixture.json'

const F = fixture as unknown as { monat: AktuellerMonatResponse; jahr: AktuellerMonatResponse }
const ALLE: Array<[string, AktuellerMonatResponse]> = [['Monat', F.monat], ['Jahr', F.jahr]]

describe('N-633 — Dienstwagen: der Posten führt Hauptbuch und Tabelle auf das Ergebnis', () => {
  it.each(ALLE)('%s: Antwort trägt den Posten (78 €) und das Ergebnis 44 €', (_n, d) => {
    expect(d.dienstliche_ladekosten_euro).toBe(78)
    expect(d.ergebnis_euro).toBeCloseTo(44, 2)
  })

  it.each(ALLE)('%s: T-Konto-Hauptbuch == ergebnis_euro', (_n, d) => {
    expect(baueTKonto(d).nettoT).toBeCloseTo(d.ergebnis_euro!, 2)
  })

  it.each(ALLE)('%s: Komponenten-Tabelle − Stromrechnung == ergebnis_euro', (_n, d) => {
    expect(komponentenFinanzSaldo(d) - (d.netzbezug_kosten_euro ?? 0)).toBeCloseTo(d.ergebnis_euro!, 2)
  })

  it.each(ALLE)('%s: SOLL-Zeile „Dienstliche Ladekosten" mit dem freigegebenen Hinweis', (_n, d) => {
    const z = baueTKonto(d).sollPosten.filter((p) => p.label === 'Dienstliche Ladekosten')
    expect(z).toHaveLength(1)
    expect(z[0].wert).toBe(78)
    expect(z[0].formel).toBe(DIENSTLICHE_LADEKOSTEN_HINWEIS)
  })

  it('A6: im Monat stehen die eingesetzten Werte daneben, im Jahr (Σ über Monate) nicht', () => {
    const monat = baueTKonto(F.monat).sollPosten.find((p) => p.label === 'Dienstliche Ladekosten')!
    expect(monat.berechnung).toBe('200,0 kWh PV × 30,00 ct/kWh + 100,0 kWh Netz × 18,00 ct/kWh')
    const jahr = baueTKonto(F.jahr).sollPosten.find((p) => p.label === 'Dienstliche Ladekosten')!
    expect(jahr.berechnung).toBeUndefined()
  })

  it('der Hinweis ist der freigegebene Wortlaut', () => {
    expect(DIENSTLICHE_LADEKOSTEN_HINWEIS).toBe(
      'Strom für den Dienstwagen: Netzanteil zum Wallbox-Tarif, PV-Anteil zum Netzbezugspreis. '
      + 'Die Erstattung des Arbeitgebers steht unter den sonstigen Erträgen.')
  })

  it('ohne Posten keine Zeile (0 und fehlendes Feld)', () => {
    for (const ohne of [{ dienstliche_ladekosten_euro: 0 }, { dienstliche_ladekosten_euro: undefined }]) {
      const d = { ...F.monat, ...ohne }
      expect(baueTKonto(d).sollPosten.some((p) => p.label === 'Dienstliche Ladekosten')).toBe(false)
    }
  })
})
