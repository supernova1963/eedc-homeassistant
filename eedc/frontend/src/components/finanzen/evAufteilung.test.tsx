/**
 * Zwei Sichten, eine Zahl — die PV-Zeile der Komponenten-Finanztabelle darf
 * nicht beanspruchen, was die Komponentenzeilen darunter schon tragen (#402).
 *
 * **Der Melder.** rilmor-mhrs stellte *Cockpit → Monat → Finanzen* und das
 * SOLL/HABEN-T-Konto nebeneinander: „PV-Anlage" 267,87 € gegen
 * „PV-Eigenverbrauch-Ersparnis" 143,51 €. Die Differenz war auf den Cent die
 * Summe seiner drei Komponentenzeilen (BKW 16,53 + Speicher 10,92 + Victron
 * 96,91 = 124,36 €) — dieselbe Kilowattstunde einmal voll und einmal als
 * Spread. Sein Zahlenbild ist hier maßstabsgetreu nachgebaut.
 *
 * ⚠ Die Probe braucht **beide** Komponentenarten. Bei einer reinen PV-Anlage
 * ist `evInKomponentenzeilen` null, und ein kaputter Abzug bliebe grün.
 *
 * Geschwister: TKonto.test.tsx · KomponentenFinanzTabelle.mobil.test.tsx
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { KomponentenFinanzTabelle } from './KomponentenFinanzTabelle'
import { evInKomponentenzeilen, pvEigenverbrauchRestEuro } from './evAufteilung'
import { aktuellerMonat } from '../../test/factories'
import type { InvestitionFinancialDetail } from '../../api/aktuellerMonat'

const zeile = (
  id: number, bezeichnung: string, typ: string, ersparnis: number,
  extra: Partial<InvestitionFinancialDetail> = {},
): InvestitionFinancialDetail => ({
  investition_id: id, bezeichnung, typ,
  betriebskosten_monat_euro: 0, erloes_euro: null, erloes_formel: null,
  ersparnis_euro: ersparnis, ersparnis_label: 'Ersparnis',
  formel: null, berechnung: null,
  sonstige_ertraege_euro: 0, sonstige_ausgaben_euro: 0,
  ...extra,
})

// Roberts Anlage (August 2026), auf die relevanten Größen reduziert.
const robert = aktuellerMonat(2026, 8, {
  anlage_name: 'Robert',
  einspeise_erloes_euro: 0,
  ev_ersparnis_euro: 267.87,
  netzbezug_kosten_euro: 10.84,
  investitionen_financials: [
    zeile(1, 'BKW', 'balkonkraftwerk', 16.53),
    zeile(2, 'DG-Speicher', 'speicher', 10.92),
    zeile(3, 'Victron', 'speicher', 96.91),
    zeile(4, 'Daikin Stylish', 'waermepumpe', 0.39),
    zeile(5, 'NIU NQiX 500', 'e-auto', 10.39, { betriebskosten_monat_euro: 4.17 }),
  ],
})

describe('evAufteilung', () => {
  it('nennt den Anteil, der schon als Komponentenzeile ausgewiesen ist', () => {
    expect(evInKomponentenzeilen(robert.investitionen_financials!)).toBeCloseTo(124.36, 2)
  })

  it('lässt der PV-Anlage genau den Rest — die Zahl des T-Kontos', () => {
    expect(pvEigenverbrauchRestEuro(robert)).toBeCloseTo(143.51, 2)
  })

  it('zählt eine Wärmepumpen- oder E-Auto-Ersparnis NICHT dazu', () => {
    // Sie stecken nicht in `ev_ersparnis_euro` — wer sie abzöge, nähme der
    // PV-Zeile etwas weg, das sie zu Recht trägt (Gegenrichtung des Fehlers).
    const nurWp = { ...robert, investitionen_financials: [zeile(4, 'WP', 'waermepumpe', 50)] }
    expect(evInKomponentenzeilen(nurWp.investitionen_financials!)).toBe(0)
    expect(pvEigenverbrauchRestEuro(nurWp)).toBeCloseTo(267.87, 2)
  })

  it('zieht die PV-Ladung der Wallbox ab, andere Wallbox-Ersparnisse nicht', () => {
    const mitWb = (label: string) => ({
      ...robert,
      investitionen_financials: [zeile(9, 'Wallbox', 'wallbox', 20, { ersparnis_label: label })],
    })
    expect(evInKomponentenzeilen(mitWb('PV-Ladung-Ersparnis').investitionen_financials!)).toBe(20)
    expect(evInKomponentenzeilen(mitWb('Ersparnis vs. Verbrenner').investitionen_financials!)).toBe(0)
  })
})

describe('KomponentenFinanzTabelle', () => {
  it('zeigt in der PV-Zeile den Rest, nicht die volle Eigenverbrauchs-Ersparnis', () => {
    render(<KomponentenFinanzTabelle d={robert} />)
    expect(screen.getAllByText('143,51').length).toBeGreaterThan(0)
    expect(screen.queryByText('267,87')).toBeNull()
  })

  it('sagt an der PV-Zeile, dass der Anteil der Komponenten fehlt', () => {
    render(<KomponentenFinanzTabelle d={robert} />)
    expect(screen.getAllByText(/ohne Anteil der Komponenten unten/).length).toBeGreaterThan(0)
  })

  it('lässt den Hinweis weg, wo es nichts abzuziehen gibt', () => {
    const nurPv = { ...robert, investitionen_financials: [] }
    render(<KomponentenFinanzTabelle d={nurPv} />)
    expect(screen.queryByText(/ohne Anteil der Komponenten unten/)).toBeNull()
  })

  it('die Summe der Einsparungen bleibt die anlagenweite Ersparnis', () => {
    // Der eigentliche Befund: 267,87 + 124,36 wäre die Doppelzählung.
    // Σ Einsparungen = 143,51 + 16,53 + 10,92 + 96,91 + 0,39 + 10,39 = 278,65 —
    // und 278,65 ist zugleich das Σ HABEN des T-Kontos für denselben Monat.
    render(<KomponentenFinanzTabelle d={robert} />)
    expect(screen.getAllByText('278,65').length).toBeGreaterThan(0)
    expect(screen.queryByText('403,01')).toBeNull()
  })
})
