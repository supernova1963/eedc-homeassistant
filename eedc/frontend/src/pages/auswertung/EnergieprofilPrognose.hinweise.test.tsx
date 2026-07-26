/**
 * P4-Ehrlichkeit im Frontend: die Tagesprognose zeigt ihre Hinweise (A17).
 *
 * Das Backend füllt seit A17 `TagesPrognose.hinweise`, wenn das PV-Profil nicht
 * das ist, was der Name verspricht (24 Nullen weil jeder Prognose-Pfad ausfiel;
 * Solcast-Profil von heute als Näherung für morgen). Ein `hinweise`-Eintrag, den
 * keine Sicht rendert, wäre dasselbe Schweigen mit mehr Code — deshalb prüft
 * dieser Test die Anzeige, nicht das Feld.
 *
 * Gerendert wird über die geteilte `HerkunftZeile` (Regel 0a — dieselbe Zeile,
 * die im Komponenten-Hub „nach kWp gerechnet" trägt), keine neue Komponente.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PrognoseChartKarte, PrognoseTabelle } from './EnergieprofilPrognose'
import { ThemeProvider } from '../../context/ThemeContext'
import type { TagesPrognose } from '../../api/energie_profil'

const HINWEIS = 'Für diesen Tag liegt keine PV-Prognose vor — der Wetterabruf ist '
  + 'ausgefallen. Die PV-Werte im Verlauf sind deshalb 0 und bedeuten NICHT, dass '
  + 'die Anlage nichts erzeugt; auch die Speicher-Vorschau darunter ist damit ohne '
  + 'Aussage.'

function daten(hinweise: string[]): TagesPrognose {
  return {
    datum: '2026-07-27',
    stunden: Array.from({ length: 24 }, (_, stunde) => ({
      stunde, pv_kw: 0, verbrauch_kw: 0.5, netto_kw: -0.5,
      netzbezug_kw: 0.5, einspeisung_kw: 0, soc_prozent: null,
    })),
    pv_summe_kwh: 0,
    verbrauch_summe_kwh: 12,
    netzbezug_summe_kwh: 12,
    einspeisung_summe_kwh: 0,
    eigenverbrauch_kwh: 0,
    autarkie_prozent: 0,
    speicher_kapazitaet_kwh: null,
    speicher_voll_um: null,
    speicher_leer_um: null,
    verbrauch_basis: 'tagestyp',
    pv_quelle: 'openmeteo',
    daten_tage: 14,
    hinweise,
  }
}

describe('Tagesprognose — Unvollständigkeit steht in der Sicht', () => {
  beforeEach(() => {
    // `useChartTheme` fragt das System-Theme ab; jsdom kennt matchMedia nicht.
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: false, media: '', onchange: null,
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
      addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
    }))
  })

  it('Chart-Karte zeigt Badge und Erklärsatz über den Kennzahlen', () => {
    render(<ThemeProvider><PrognoseChartKarte daten={daten([HINWEIS])} /></ThemeProvider>)
    // SoT-Badge (iconOnly, aria-label aus ZUSTAND_META) — Zustand „weicht ab",
    // weil die Zahl nicht geschätzt, sondern unvollständig ist.
    expect(screen.getByLabelText('weicht ab (unvollständig)')).toBeInTheDocument()
    // Bezugs-Label der Herkunftszeile + Titel der KPI-Kachel — beide „PV-Prognose",
    // die Kennzeichnung steht also unmittelbar an der betroffenen Zahl.
    expect(screen.getAllByText('PV-Prognose')).toHaveLength(2)
    expect(screen.getByText(/keine PV-Prognose vor/)).toBeInTheDocument()
    // Der Wert selbst bleibt stehen — beschriftet, nicht ersetzt (PV-Summe und
    // Einspeisung sind beide 0, deshalb mehrere Treffer).
    expect(screen.getAllByText('0,0 kWh').length).toBeGreaterThan(0)
  })

  it('Tabelle zeigt die Kennzeichnung ebenfalls (Fokus-Overlay zeigt sie allein)', () => {
    render(<PrognoseTabelle daten={daten([HINWEIS])} />)
    expect(screen.getByLabelText('weicht ab (unvollständig)')).toBeInTheDocument()
    expect(screen.getByText(/keine PV-Prognose vor/)).toBeInTheDocument()
  })

  it('ohne Hinweise bleibt beide Sichten unmarkiert', () => {
    const { unmount } = render(<ThemeProvider><PrognoseChartKarte daten={daten([])} /></ThemeProvider>)
    expect(screen.queryByLabelText(/weicht ab/)).not.toBeInTheDocument()
    unmount()

    render(<PrognoseTabelle daten={daten([])} />)
    expect(screen.queryByLabelText(/weicht ab/)).not.toBeInTheDocument()
  })
})
