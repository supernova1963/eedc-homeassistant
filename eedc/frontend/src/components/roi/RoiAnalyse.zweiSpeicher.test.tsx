/**
 * ROI-Detailübersicht: der aufgeklappte Streifen gehört zu EINEM Gerät — und sagt zu welchem.
 *
 * **Der gemeldete Fall (Radiocarbonat, simon42 T89667 #294, 02.09.2026).** Seine
 * Zeile heißt „PV-System Multiplus II · inkl. Speicher Voltsmile alt (5,12 kWh),
 * Voltsmile (10,24 kWh)" — zwei Speicher, weil er im Mai aufgerüstet, den alten
 * stillgelegt und den neuen neu angelegt hat. Darunter stand **ein** Wirkungsgrad
 * (79,1 %) ohne Angabe, zu welchem der beiden er gehört.
 *
 * **Die Ursache war `find` gegen `filter`.** Die Zeilenüberschrift baut ihre Liste
 * mit `filter` (alle Speicher), der Streifen zog sein Detail mit `.find(...)` — also
 * den **ersten**. Sortiert wird nach Typ mit Tiebreaker ID aufsteigend
 * (`sort_investitionen_nach_typ`), und ohne `jahr`-Parameter greift kein
 * Aktiv-Filter (Absicht seit #123: ROI historisch) ⇒ gezeigt wurde der **älteste**,
 * bei einem Speicher-Tausch also der stillgelegte. Sein eigener Bildschirmfoto
 * belegt die Reihenfolge: „Voltsmile alt" steht vorn.
 *
 * ⚠ **Und die zweite Hälfte, die beim Bau fast danebengegangen wäre:** Der Streifen
 * stellt zwei Größen mit **verschiedenen Bezugsobjekten** nebeneinander. Der
 * effektive Ladepreis kommt aus `speicher_ladepreis_anlage` und ist **anlagenweit**
 * (ein Aufruf je Anlage, `crud.py:1579`), der Wirkungsgrad aus
 * `speicher_eta_by_inv[inv.id]` und gehört **einem Gerät**. Ein naives „je Speicher
 * eine Zeile" hätte den anlagenweiten Preis unter jedes Gerät geschrieben und damit
 * eine Messung am Gerät behauptet, die es nicht gibt — dieselbe Klasse, die dieser
 * Bau behebt. Deshalb steht der Preis genau **einmal**.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const speicherDetail = (eta: number) => ({
  modus: 'ist',
  // Anlagenweit — beide Speicher tragen denselben Wert, so liefert es das Backend.
  effektiver_ladepreis_cent: 12.5,
  ladepreis_quelle: 'tep',
  verwendetes_wirkungsgrad_prozent: eta,
  wirkungsgrad_quelle: 'fenster_lang',
})

vi.mock('../../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api')>()),
  investitionenApi: {
    getROIDashboard: vi.fn(() => Promise.resolve({
      gesamt_investition: 20000,
      gesamt_relevante_kosten: 20000,
      gesamt_sonstige_ausgaben_euro: 0,
      gesamt_kapitaleinsatz: 20000,
      gesamt_jahres_einsparung: 1200,
      gesamt_roi_prozent: 6,
      gesamt_amortisation_jahre: 16,
      gesamt_co2_einsparung_kg: 1000,
      benzinpreis_hinweis_euro: 1.7,
      berechnungen: [{
        investition_id: 1, investition_typ: 'pv-system',
        investition_bezeichnung: 'PV-System Multiplus II',
        relevante_kosten: 20000, kapitaleinsatz: 20000,
        anschaffungskosten: 20000, anschaffungskosten_alternativ: 0,
        jahres_einsparung: 1200, roi_prozent: 6, amortisation_jahre: 16, co2_einsparung_kg: 1000,
        detail_berechnung: null,
        komponenten: [
          // Reihenfolge wie im Backend: ID aufsteigend ⇒ der stillgelegte zuerst.
          { investition_id: 11, bezeichnung: 'Voltsmile alt (5.12 kWh)', typ: 'speicher',
            kosten: 4000, kosten_alternativ: 0, relevante_kosten: 4000,
            einsparung: 200, co2_einsparung_kg: 100, detail: speicherDetail(79.1) },
          { investition_id: 12, bezeichnung: 'Voltsmile (10.24 kWh)', typ: 'speicher',
            kosten: 8000, kosten_alternativ: 0, relevante_kosten: 8000,
            einsparung: 500, co2_einsparung_kg: 300, detail: speicherDetail(93.4) },
        ],
      }],
    })),
  },
}))

vi.mock('../../api/aussichten', () => ({
  aussichtenApi: { getFinanzPrognose: vi.fn(() => Promise.reject(new Error('nicht Teil dieser Probe'))) },
}))

import { RoiAnalyse } from './RoiAnalyse'

async function streifenOeffnen() {
  render(<RoiAnalyse anlageId={1} />)
  const name = (await screen.findAllByText(/PV-System Multiplus II/))[0]
  const zeile = name.closest('tr')!
  const knopf = zeile.querySelector('button')!
  fireEvent.click(knopf)
  return zeile.closest('tbody')!
}

describe('ROI-Detailübersicht mit zwei Speichern (Radiocarbonat #294)', () => {
  it('nennt BEIDE Speicher mit ihrem eigenen Wirkungsgrad — nicht nur den ersten', async () => {
    const body = await streifenOeffnen()
    const text = body.textContent ?? ''
    // Vor dem Fix stand hier ausschließlich 79,1 % — der Wert des stillgelegten
    // Geräts, unbeschriftet, für die ganze Zeile.
    expect(text).toContain('79,1 %')
    expect(text).toContain('93,4 %')
    // Und beide Werte tragen den Namen ihres Geräts.
    expect(text).toContain('Voltsmile alt (5.12 kWh)')
    expect(text).toContain('Voltsmile (10.24 kWh)')
  })

  it('zeigt den anlagenweiten Ladepreis genau EINMAL, nicht je Speicher', async () => {
    const body = await streifenOeffnen()
    const text = body.textContent ?? ''
    // Er ist eine Größe der Anlage, keine Messung am einzelnen Gerät — ihn zu
    // wiederholen behauptete das Gegenteil.
    expect(text.match(/12,50 ct\/kWh/g) ?? []).toHaveLength(1)
    expect(text.match(/Effektiver Ladepreis/g) ?? []).toHaveLength(1)
    // Bei mehreren Speichern sagt die Beschriftung, worauf er sich bezieht.
    expect(text).toContain('Effektiver Ladepreis (Anlage)')
  })

  it('bleibt bei EINEM Speicher unverändert — kein Gerätename, keine Anlagen-Klammer', async () => {
    // Zusicherung für die große Mehrheit: wer einen Speicher hat, sieht genau
    // das, was er vorher gesehen hat.
    const { investitionenApi } = await import('../../api')
    vi.mocked(investitionenApi.getROIDashboard).mockResolvedValueOnce({
      gesamt_investition: 8000, gesamt_relevante_kosten: 8000, gesamt_sonstige_ausgaben_euro: 0,
      gesamt_kapitaleinsatz: 8000, gesamt_jahres_einsparung: 500, gesamt_roi_prozent: 6,
      gesamt_amortisation_jahre: 16, gesamt_co2_einsparung_kg: 300, benzinpreis_hinweis_euro: 1.7,
      berechnungen: [{
        investition_id: 2, investition_typ: 'speicher', investition_bezeichnung: 'BYD HVS 10',
        relevante_kosten: 8000, kapitaleinsatz: 8000, anschaffungskosten: 8000,
        anschaffungskosten_alternativ: 0, jahres_einsparung: 500, roi_prozent: 6,
        amortisation_jahre: 16, co2_einsparung_kg: 300,
        detail_berechnung: speicherDetail(93.4), komponenten: [],
      }],
    } as never)
    render(<RoiAnalyse anlageId={1} />)
    const name = (await screen.findAllByText(/BYD HVS 10/))[0]
    const zeile = name.closest('tr')!
    fireEvent.click(zeile.querySelector('button')!)
    const text = zeile.closest('tbody')!.textContent ?? ''
    expect(text).toContain('Effektiver Ladepreis:')
    expect(text).not.toContain('(Anlage)')
    expect(text).toContain('93,4 %')
  })

  it('zeigt die Degradations-Warnung NICHT mehr in der ROI-Sicht (Entscheid 03.09.2026)', async () => {
    // Sie kann hier per Konstruktion nur erscheinen, wenn der gepflegte Wert
    // gerade NICHT verwendet wird: gesetzt wurde sie unter
    // `eta_ist.wirkungsgrad_prozent is not None`, und genau dann gibt
    // `_aufloesen_wirkungsgrad` die MESSUNG zurück. Sie bleibt im
    // Komponenten-Hub, wo der gepflegte Wert zählt (Sizing, Tages-Vorschau,
    // HA-Sensoren) — hier gehört sie nicht hin.
    const body = await streifenOeffnen()
    const text = body.textContent ?? ''
    expect(text).not.toContain('Degradation')
    expect(text).not.toContain('Parameter-Wert')
  })
})
