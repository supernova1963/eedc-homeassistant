/**
 * N-444 — die Client-Hälfte: was die beiden Quotienten aus den Fixture-Zahlen
 * machen, vor und nach dem Bau.
 *
 * ⚠ **STATUS: FIXTURE AUS DER VORLAGE WK-05 — NICHT GEFAHREN.**
 * Ziel-Ablage im BAU: `eedc/frontend/src/v4/KomponentenSektionen.n444.test.tsx`.
 * Braucht Lauf: `cd eedc/frontend && npm run test -- KomponentenSektionen.n444`.
 *
 * ⛔ **Der Fix ist backend-seitig** (`snapshot/aggregator.py`: Fenster je Typ).
 * Diese Probe ändert am Client nichts — sie **pinnt**, was die Zahlen aus dem
 * Backend hier anrichten, und zwar in beide Richtungen:
 *
 *  1. `VOR`-Fall: die Backend-Zahlen aus dem alten Fenster ⇒ die € und der
 *     PV-Anteil, die ein Anwender heute sieht.
 *  2. `NACH`-Fall: dieselbe Anlage, dieselbe Nacht, Zahlen aus EINEM Fenster.
 *
 * Zahlen aus `test_n444_tagesdetail_ein_fenster.py` (Fall „Nachtladung nach
 * 23 Uhr"): Tages-Ladung 4,0 kWh · Entladung 3,0 kWh · Netzladung laut Zähler
 * 6,0 kWh ([0,24)) bzw. 0,0 kWh (Fenster der Tageszeile). Einspeisepreis 8 ct,
 * Bezugspreis 32 ct.
 *
 * ⚠ **Die Kappung `Math.min(1, …)` bleibt danach erreichbar** — und das ist
 * kein Restversatz, sondern eine zweite Ursache: der Zähler ist eine **Brutto**-
 * Menge (`ladung_netz_kwh`), der Nenner eine **Netto**-Menge
 * (`Σ max(0, −batterie_kw)`, s. N-197). Der letzte Fall hält das fest, damit
 * niemand die Kappung nach dem Fenster-Bau für erledigt hält.
 */
import { describe, it, expect } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { isValidElement } from 'react'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import type { Block } from '../components/blocks'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import { aktuellerMonat, tagWerte } from '../test/factories'
import { baueTagKpis } from './TagBilanz'

const d = (over: Partial<AktuellerMonatResponse> = {}) => aktuellerMonat(2026, 1, over)

function renderBlock(bloecke: Block[], id: string) {
  const node = bloecke.find((b) => b.id === id)?.render(false)
  if (!isValidElement(node)) throw new Error(`Block ${id} rendert nicht`)
  return render(node)
}

/** Der Tag aus der Backend-Fixture, ohne die beiden strittigen Größen.
 *
 * Päckchen BB: Betrag, Teile und Kappung der Wirkungsverluste rechnet seitdem das Backend (Layer
 * `speicher_bilanz`, bitgleich zur früheren Client-Formel — `test_bb_speicher_tag_felder.py`); die Fälle tragen die
 * Felder deshalb so, wie die Antwort sie liefert. */
const TAG_SPEICHER = {
  speicher_ladung_kwh: 4.0,
  speicher_entladung_kwh: 3.0,
  einspeise_preis_cent: 8,
  netzbezug_preis_cent: 32,
} as Partial<AktuellerMonatResponse>

/** «Nach dem Bau» (Netzladung 0 aus dem Fenster der Tageszeile): 1,0 kWh Verlust, ganz PV ⇒ 1,0 × 8 ct. */
const NACH_FELDER = {
  speicher_ladung_netz_kwh: 0.0, speicher_bilanz_kwh: -1.0, speicher_wirkungsverluste_euro: 0.08,
  speicher_verlust_pv_kwh: 1.0, speicher_verlust_netz_kwh: 0, speicher_netzladung_anteil_gekappt: false,
} as Partial<AktuellerMonatResponse>

describe('N-444 · Speicher-Wirkungsverluste', () => {
  it('VOR dem Bau: Netzladung aus [0,24) sprengt ihren Bezug — Kappung, 0,32 €', () => {
    // 6,0 ÷ 4,0 = 1,5 → Math.min(1, …) = 1,0 ⇒ Verlust 1,0 kWh × 32 ct.
    const bloecke = baueKomponentenBloecke(
      d({ ...TAG_SPEICHER, speicher_ladung_netz_kwh: 6.0, speicher_bilanz_kwh: -1.0,
          speicher_wirkungsverluste_euro: 0.32, speicher_verlust_pv_kwh: 0, speicher_verlust_netz_kwh: 1.0,
          speicher_netzladung_anteil_gekappt: true }),
    )
    renderBlock(bloecke, 'k-speicher')
    expect(screen.getByText('−0,32 €')).toBeInTheDocument()
    // Und die Detailzeile behauptet 6 kWh „davon" 4,0 kWh.
    expect(screen.getByText('6 kWh')).toBeInTheDocument()
  })

  it('NACH dem Bau: beide Größen aus einem Fenster — 0,08 €', () => {
    // 0,0 ÷ 4,0 = 0 ⇒ Verlust 1,0 kWh × 8 ct entgangene Einspeisung.
    const bloecke = baueKomponentenBloecke(
      d({ ...TAG_SPEICHER, ...NACH_FELDER }),
    )
    renderBlock(bloecke, 'k-speicher')
    expect(screen.getByText('−0,08 €')).toBeInTheDocument()
  })

  it('⚠ die Kappung bleibt erreichbar: Brutto-Zähler gegen Netto-Nenner (N-197)', () => {
    // Eine Stunde mit 2,0 kWh Netzladung und 1,5 kWh Entladung ergibt netto
    // −0,5 kWh. Der Nenner kennt nur das Netto, der Zähler zählt brutto.
    const bloecke = baueKomponentenBloecke(
      d({ ...TAG_SPEICHER, speicher_ladung_kwh: 0.5, speicher_entladung_kwh: 0.2,
          speicher_ladung_netz_kwh: 2.0, speicher_bilanz_kwh: -0.3, speicher_wirkungsverluste_euro: (0.3 * 32) / 100,
          speicher_verlust_pv_kwh: 0, speicher_verlust_netz_kwh: 0.3, speicher_netzladung_anteil_gekappt: true }),
    )
    renderBlock(bloecke, 'k-speicher')
    // Verlust 0,3 kWh × 100 % Netz × 32 ct = 0,10 € — die Kappung greift.
    expect(screen.getByText('−0,10 €')).toBeInTheDocument()

    // ⭐ K2 (Gernot 12.09.): Sie greift nicht mehr STUMM. Der Grund steht im
    // bestehenden Formel-Tooltip — er erscheint erst beim Zeigen.
    fireEvent.mouseEnter(screen.getByText('Wirkungsverluste (Opportunitätskosten)'))
    expect(screen.getAllByText(/Netz-Anteil auf 100 % begrenzt/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Ladung und Entladung in derselben Stunde/).length)
      .toBeGreaterThan(0)
  })

  it('GEGENPROBE — ohne Kappung steht kein Grund im Tooltip', () => {
    const bloecke = baueKomponentenBloecke(
      d({ ...TAG_SPEICHER, ...NACH_FELDER }),
    )
    renderBlock(bloecke, 'k-speicher')
    fireEvent.mouseEnter(screen.getByText('Wirkungsverluste (Opportunitätskosten)'))
    expect(screen.queryByText(/Netz-Anteil auf 100 % begrenzt/)).toBeNull()
    // Und die Herleitung steht trotzdem da — sonst hätte der Bau sie verdrängt.
    expect(screen.getAllByText(/1,0 kWh × 8,00 ct \(entg. Einspeisung\)/).length)
      .toBeGreaterThan(0)
  })
})

// Päckchen BB2: den PV-Anteil rechnet seitdem das Backend (`emob_pv_anteil_prozent`, Layer `pv_anteil_ladung`,
// bitgleich zur früheren Client-Formel — `test_bb_speicher_tag_felder.py`); die Fälle tragen das Feld wie die Antwort.
describe('N-444 · PV-Anteil der E-Mobilität', () => {
  it('VOR dem Bau: Teile aus [0,24) über einem Ganzen aus der Tageszeile', () => {
    // Nachtladung 8,0 kWh aus dem Netz nach 23 Uhr: der Zähler sieht sie,
    // die Tageszeile nicht ⇒ „Netz-Anteil 8,0 kWh" unter „Ladung gesamt 9,0".
    const bloecke = baueKomponentenBloecke(
      d({ emob_ladung_kwh: 9.0, emob_ladung_pv_kwh: 9.0, emob_ladung_netz_kwh: 8.0, emob_pv_anteil_prozent: 100 }),
    )
    renderBlock(bloecke, 'k-emob')
    expect(screen.getByText('Ladung · Netz-Anteil')).toBeInTheDocument()
    expect(screen.getByText('8 kWh')).toBeInTheDocument()
    // 9,0 ÷ 9,0 = 100 % PV — neben 8 kWh Netzladung.
    expect(screen.getByText('100')).toBeInTheDocument()
  })

  it('NACH dem Bau: PV + Netz decken die Ladung', () => {
    const bloecke = baueKomponentenBloecke(
      d({ emob_ladung_kwh: 17.0, emob_ladung_pv_kwh: 9.0, emob_ladung_netz_kwh: 8.0,
        emob_pv_anteil_prozent: (9.0 / 17.0) * 100 }),
    )
    renderBlock(bloecke, 'k-emob')
    // 9,0 ÷ 17,0 = 52,9 % → gerundet 53
    expect(screen.getByText('53')).toBeInTheDocument()
  })
})

describe('N-444/K3 · die KPI „Batterieladung Netz" nennt beide Herkünfte', () => {
  // ⛔ Kein Rechenfix, sondern eine Ehrlichkeit: Menge und Preis stammen aus
  // verschiedenen Quellen mit verschiedenen Netzladungs-Begriffen. Seit N-444
  // liegen sie wenigstens im selben Fenster; die Definitionsdifferenz gehört zu
  // N-197/N-290 und wird hier benannt, nicht geheilt.
  it('die Formel sagt Zähler UND Ladestunden, nicht nur „Netzladung"', () => {
    const k = baueTagKpis(
      tagWerte('2026-07-25', { erzeugung: 7 }), null, null,
      { kwh: 2.5, preis_cent: 22.5, kosten_euro: 0.5625 },
    ).find((x) => x.title === 'Batterieladung Netz')!
    expect(k).toBeDefined()
    expect(k.formel).toMatch(/Netzladungs-Zähler/)
    expect(k.formel).toMatch(/Ladestunden/)
    // Die Zahl selbst ist unberührt — der Bau ändert hier nur den Text.
    expect(k.ergebnis).toBe('= 0,56 €')
  })
})
