import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { ThemeProvider } from '../../context/ThemeContext'
import { stubMatchMedia } from '../../test/render'
import { LEER_TOKEN } from '../../lib'
import { SpeicherDeepDive, EAutoDeepDive } from './CommunityKomponentenTeile'
import type { CommunityBenchmarkResponse, SpeicherByClass, EAutoByUsage } from '../../api/community'

// ─── N-745 (12.10.2026): «unbekannt» ist nicht 0 ──────────────────────────────
//
// Der Community-Server liefert für eine Speicher-Kapazitätsklasse mit weniger als
// drei Werten bewusst KEINEN Median (`eedc-community/backend/api/components.py`,
// `_median`: «lieber ein ehrliches —»). Die Klassentabelle machte daraus mit
// `?? 0` die Zeile «0 · 0,0 %» — live am 12.10.2026 für die Klasse bis 5 kWh
// (11 Anlagen, ein Wirkungsgradwert). Dieselbe Klasse in der E-Auto-Tabelle:
// eine Nutzungsklasse ohne bildbaren PV-Anteil/Verbrauch (Server `None`) stand
// als «0 %» / «0,0 kWh/100km» da.
//
// Mitgeprüft: die «(Du)»-Markierung der kleinsten Speicherklasse. Der Client
// verglich «bis 5 kWh» mit dem selbst erzeugten Label «0-5 kWh» — nie gleich.

beforeEach(() => {
  stubMatchMedia()
})

// Live-Form `GET /api/components/speicher/by-class`, 12.10.2026 (öffentliche API).
const SPEICHER_KLASSEN: SpeicherByClass = {
  klassen: [
    { von_kwh: 0, bis_kwh: 5, anzahl: 11, durchschnitt_wirkungsgrad: null, durchschnitt_zyklen: null, durchschnitt_netz_anteil: 0 },
    { von_kwh: 5, bis_kwh: 10, anzahl: 49, durchschnitt_wirkungsgrad: 93.4, durchschnitt_zyklen: 231.9, durchschnitt_netz_anteil: 0 },
    { von_kwh: 10, bis_kwh: 15, anzahl: 42, durchschnitt_wirkungsgrad: 93.5, durchschnitt_zyklen: 221.3, durchschnitt_netz_anteil: 0 },
    { von_kwh: 15, bis_kwh: null, anzahl: 53, durchschnitt_wirkungsgrad: 92.7, durchschnitt_zyklen: 144.9, durchschnitt_netz_anteil: 0 },
  ],
}

function speicherBenchmark(kwh: number): CommunityBenchmarkResponse {
  return {
    anlage: { speicher_kwh: kwh },
    benchmark_erweitert: { speicher: { kapazitaet: { wert: kwh }, wirkungsgrad: { wert: 91 } } },
  } as unknown as CommunityBenchmarkResponse
}

function zeileZu(label: string): HTMLElement {
  const zelle = screen.getAllByText(label).find((el) => el.closest('tr'))
  if (!zelle) throw new Error(`keine Tabellenzeile «${label}»`)
  return zelle.closest('tr') as HTMLElement
}

describe('Speicher-Klassentabelle: Server-null bleibt «—»', () => {
  it('zeigt für die Klasse 0–5 kWh ohne Median «—» statt 0 und 0,0 %', () => {
    render(<ThemeProvider><SpeicherDeepDive benchmark={speicherBenchmark(10)} communityStats={SPEICHER_KLASSEN} /></ThemeProvider>)
    const zellen = within(zeileZu('0-5 kWh')).getAllByRole('cell')
    expect(zellen[1]).toHaveTextContent(LEER_TOKEN)
    expect(zellen[2]).toHaveTextContent(LEER_TOKEN)
    expect(zellen[2]).not.toHaveTextContent('%')
    expect(zellen[1]).not.toHaveTextContent(/^0$/)
    // Gegenprobe: eine Klasse mit Werten bleibt unverändert formatiert.
    const voll = within(zeileZu('5-10 kWh')).getAllByRole('cell')
    expect(voll[1]).toHaveTextContent('232')
    expect(voll[2]).toHaveTextContent('93,4 %')
  })

  it('markiert einen Speicher unter 5 kWh in seiner Klasse mit «(Du)»', () => {
    render(<ThemeProvider><SpeicherDeepDive benchmark={speicherBenchmark(4)} communityStats={SPEICHER_KLASSEN} /></ThemeProvider>)
    expect(within(zeileZu('0-5 kWh')).getByText('(Du)')).toBeInTheDocument()
  })
})

const EAUTO_KLASSEN: EAutoByUsage = {
  klassen: [
    { klasse: 'wenig', beschreibung: '<500 km/Monat', anzahl: 2, durchschnitt_pv_anteil: null, durchschnitt_verbrauch_100km: null },
    { klasse: 'viel', beschreibung: '>1000 km/Monat', anzahl: 23, durchschnitt_pv_anteil: 39.9, durchschnitt_verbrauch_100km: 16.8 },
  ],
}

describe('E-Auto-Nutzungstabelle: Server-null bleibt «—»', () => {
  it('zeigt für eine Klasse ohne bildbaren Wert «—» statt 0 %', () => {
    const benchmark = { anlage: {}, benchmark_erweitert: { eauto: { pv_anteil: { wert: 60 } } } } as unknown as CommunityBenchmarkResponse
    render(<ThemeProvider><EAutoDeepDive benchmark={benchmark} communityStats={EAUTO_KLASSEN} /></ThemeProvider>)
    const leer = within(zeileZu('Wenig')).getAllByRole('cell')
    expect(leer[1]).toHaveTextContent(LEER_TOKEN)
    expect(leer[1]).not.toHaveTextContent('kWh/100km')
    expect(leer[2]).toHaveTextContent(LEER_TOKEN)
    expect(leer[2]).not.toHaveTextContent('%')
    const voll = within(zeileZu('Viel')).getAllByRole('cell')
    expect(voll[1]).toHaveTextContent('16,8 kWh/100km')
    expect(voll[2]).toHaveTextContent('40 %')
  })
})
