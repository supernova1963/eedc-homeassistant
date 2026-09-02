import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { isValidElement } from 'react'
import { finanzTeaserBlock, communityBlock, MonatHeader } from './MonatRahmen'
import type { ParkApi } from '../components/park'
import type { MonatsVergleich } from '../api/community'
import { aktuellerMonat } from '../test/factories'

const d = aktuellerMonat(2025, 7, {
  netto_ertrag_euro: 128, einspeise_erloes_euro: 15, ev_ersparnis_euro: 120, netzbezug_kosten_euro: 7,
  autarkie_prozent: 61, eigenverbrauch_quote_prozent: 54, einspeisung_kwh: 189, netzbezug_kwh: 143,
})

describe('finanzTeaserBlock', () => {
  it('G20-1: Kopf-Kennzahl = Tabellen-Saldo (Kopf == sichtbare Summe)', () => {
    // Nur PV-Anlage-Zeile (Erträge 15 + Einsparungen 120 − Aufwand 0) = Saldo 135.
    const b = finanzTeaserBlock(d)!
    expect(b.id).toBe('finanzen')
    expect(b.summary).toMatch(/\+135,00 € Saldo/)
  })

  it('G20-1: Komponenten-Tabelle — Zeile je Komponente, Spalten + Summen-Saldo', () => {
    const dd = {
      ...d,
      // PV-Anlage: 15 + 120. WP: Einsparung 31,67, Aufwand (bk) 16,67. E-Auto: Einsparung
      // 65,37, Sonstige-Ertrag 185, Sonstige-Ausgabe 35. → Summen-Saldo:
      // (15+120) + (0+31,67−16,67) + (185+65,37−35) = 135 + 15 + 215,37 = 365,37
      investitionen_financials: [
        { investition_id: 2, bezeichnung: 'Daikin WP', typ: 'waermepumpe', betriebskosten_monat_euro: 16.67,
          erloes_euro: null, ersparnis_euro: 31.67, ersparnis_label: 'Ersparnis vs. Gas',
          formel: '(Wärme ÷ …) − Strom × …', berechnung: '100 kWh / 0,9 …', erloes_formel: null, sonstige_ertraege_euro: 0, sonstige_ausgaben_euro: 0 },
        { investition_id: 3, bezeichnung: 'Tesla', typ: 'e-auto', betriebskosten_monat_euro: 0,
          erloes_euro: null, ersparnis_euro: 65.37, ersparnis_label: 'Ersparnis vs. Verbrenner',
          formel: '(km × …) − …', berechnung: '651 km × 7,5 L/100km × 1,65 €', erloes_formel: null, sonstige_ertraege_euro: 185, sonstige_ausgaben_euro: 35 },
      ],
    }
    const b = finanzTeaserBlock(dd)!
    expect(b.summary).toMatch(/\+365,37 € Saldo/)
    const node = b.render(false)
    if (!isValidElement(node)) throw new Error('render() ergab kein Element')
    render(node)
    // Komponenten-Zeilen vorhanden (PV-Anlage synthetisch + WP + Tesla).
    expect(screen.getAllByText('PV-Anlage').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Daikin WP').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Tesla').length).toBeGreaterThan(0)
    // Spaltenköpfe (Desktop-Tabelle).
    expect(screen.getByText('Erträge (€)')).toBeInTheDocument()
    expect(screen.getByText('Einsparungen (€)')).toBeInTheDocument()
    expect(screen.getByText('Aufwand (€)')).toBeInTheDocument()
    expect(screen.getByText('Saldo (€)')).toBeInTheDocument()
  })

  it('G20-4: Haushaltsperspektive — Ergebnis nach Stromrechnung = Saldo − Netzbezug', () => {
    // PV-Anlage-Saldo 135 (15 + 120), Netzbezug-Kosten 7 → Ergebnis 128,00 €.
    const node = finanzTeaserBlock(d)!.render(false)
    if (!isValidElement(node)) throw new Error('render() ergab kein Element')
    render(node)
    expect(screen.getByText('Haushaltsperspektive')).toBeInTheDocument()
    expect(screen.getByText('= Ergebnis nach Stromrechnung')).toBeInTheDocument()
    // Kopf-Kennzahl (Komponenten-Saldo) bleibt unverändert 135,00 €.
    expect(finanzTeaserBlock(d)!.summary).toMatch(/\+135,00 € Saldo/)
    // Zusatz-Zeile trägt das Haushaltsergebnis (135 − 7).
    expect(screen.getByText(/^128,00 €$/)).toBeInTheDocument()
  })

  it('G20-4: keine Haushaltsperspektive ohne Netzbezug-Kosten', () => {
    const dd = { ...d, netzbezug_kosten_euro: null }
    const node = finanzTeaserBlock(dd)!.render(false)
    if (!isValidElement(node)) throw new Error('render() ergab kein Element')
    render(node)
    expect(screen.queryByText('Haushaltsperspektive')).not.toBeInTheDocument()
  })

  it('C3: Tarif-Info-Zeile zeigt flexiblen Netzbezug-Ø + Einspeisepreis', () => {
    const dd = { ...d, netzbezug_durchschnittspreis_cent: 32.5, einspeise_preis_cent: 8.2 }
    const block = finanzTeaserBlock(dd)!
    const node = block.render(false)
    if (!isValidElement(node)) throw new Error('render() ergab kein Element')
    render(node)
    expect(screen.getByText(/32,50 ct\/kWh/)).toBeInTheDocument()
    expect(screen.getByText(/\(flex\)/)).toBeInTheDocument()
    expect(screen.getByText(/Einspeisung 8,20 ct\/kWh/)).toBeInTheDocument()
  })

  it('C3: ohne Tarif-Felder keine Tarif-Zeile', () => {
    const node = finanzTeaserBlock(d)!.render(false)
    if (!isValidElement(node)) throw new Error('render() ergab kein Element')
    render(node)
    expect(screen.queryByText(/ct\/kWh/)).not.toBeInTheDocument()
  })

  it('Element-Park: alle Finanz-Elemente geparkt → kein Block (null)', () => {
    const allesGeparkt: ParkApi = {
      aktiv: true, istGeparkt: () => true, park: () => {}, entparke: () => {}, zuruecksetzen: () => {}, geparkt: [],
      registriere: () => () => {}, parkbareAnzahl: 0,
    }
    expect(finanzTeaserBlock(d, allesGeparkt)).toBeNull()
  })
})

describe('MonatHeader — C1/C2 Sicht-Aktionen', () => {
  it('C1: Aktualisieren nur im laufenden Monat', () => {
    const onReload = vi.fn()
    const { rerender } = render(<MonatHeader titel="Mai 2026" laufend d={d} onReload={onReload} />)
    screen.getByRole('button', { name: /Aktualisieren/ }).click()
    expect(onReload).toHaveBeenCalledOnce()
    rerender(<MonatHeader titel="Apr 2026" laufend={false} d={d} onReload={onReload} />)
    expect(screen.queryByRole('button', { name: /Aktualisieren/ })).not.toBeInTheDocument()
  })

  it('C2: Abschluss-Cross-Link nur laufend + offene Abschlüsse, zeigt auf Einstellungen/Daten', () => {
    render(<MonatHeader titel="Mai 2026" laufend d={d} zeigeAbschlussLink />)
    const link = screen.getByRole('link', { name: /Abschluss starten/ })
    expect(link).toHaveAttribute('href', '#/einstellungen/daten')
  })

  it('C2: kein Abschluss-Link wenn keine offenen Abschlüsse', () => {
    render(<MonatHeader titel="Mai 2026" laufend d={d} zeigeAbschlussLink={false} />)
    expect(screen.queryByRole('link', { name: /Abschluss starten/ })).not.toBeInTheDocument()
  })
})

describe('MonatHeader — Connector nennt seinen Zeitraum (#360)', () => {
  const mitConnector = (abdeckung: { abdeckung_von?: string | null; abdeckung_bis?: string | null }) => ({
    ...d,
    feld_quellen: {
      pv_erzeugung_kwh: { quelle: 'local_connector', konfidenz: 90, zeitpunkt: null, ...abdeckung },
    },
  })

  it('Teilabdeckung: Zeitraum am Badge + Tage-Satz im Tooltip', () => {
    // coolxmad #353: fünf Snapshots vom 28.–30.07., geliefert als Juli-Wert.
    render(<MonatHeader titel="Juli 2025" laufend d={mitConnector({
      abdeckung_von: '2025-07-28T14:03:00', abdeckung_bis: '2025-07-30T09:12:00',
    })} />)
    const badge = screen.getByText('Connector (28.–30.07.2025)')
    // Gemessen wird die Zeit ZWISCHEN den Zählerständen — 2 Tage, nicht 3.
    expect(badge).toHaveAttribute('title', expect.stringContaining('2 von 31 Tagen des Monats'))
    expect(badge).toHaveAttribute('title', expect.stringContaining('28.07.2025 bis 30.07.2025'))
  })

  it('volle Abdeckung ab dem Monatsersten: Badge unverändert', () => {
    render(<MonatHeader titel="Juli 2025" laufend d={mitConnector({
      abdeckung_von: '2025-07-01T00:00:00', abdeckung_bis: '2025-07-31T23:00:00',
    })} />)
    expect(screen.getByText('Connector')).toBeInTheDocument()
    expect(screen.queryByText(/Connector \(/)).not.toBeInTheDocument()
  })

  it('ohne Abdeckungs-Angabe: Badge unverändert', () => {
    render(<MonatHeader titel="Juli 2025" laufend d={mitConnector({})} />)
    expect(screen.getByText('Connector')).toBeInTheDocument()
    expect(screen.queryByText(/Connector \(/)).not.toBeInTheDocument()
  })
})

describe('communityBlock — data-gated (O4)', () => {
  it('null wenn keine Anlagen im Monat', () => {
    const v = { anzahl_anlagen: 0 } as MonatsVergleich
    expect(communityBlock(v, d, 'Mai', 2026)).toBeNull()
  })

  it('Block mit Anlagenzahl-Summary wenn Daten vorhanden', () => {
    const v = {
      anzahl_anlagen: 2,
      autarkie: { durchschnitt: 60, median: 58, min: 40, max: 80, anzahl_anlagen: 2 },
    } as MonatsVergleich
    const b = communityBlock(v, d, 'Mai', 2026)
    expect(b).not.toBeNull()
    expect(b!.id).toBe('community')
    expect(b!.summary).toMatch(/2 Anlagen im Mai/)
  })

  it('Singular bei genau einer Anlage', () => {
    const v = { anzahl_anlagen: 1 } as MonatsVergleich
    expect(communityBlock(v, d, 'Mai', 2026)!.summary).toMatch(/1 Anlage im Mai/)
  })

  it('spez.-Ertrag-Abweichung zum Median in der Summary (abs + rel)', () => {
    const v = { anzahl_anlagen: 5, spez_ertrag: { median: 131 } } as unknown as MonatsVergleich
    const dd = { ...d, spez_ertrag: 142 }
    // 142 − 131 = +11 ; 11 / 131 = +8 %
    expect(communityBlock(v, dd, 'Mai', 2026)!.summary).toMatch(/spez\. Ertrag 142 kWh\/kWp \(\+11 \/ \+8 % vs\. Median\)/)
  })

  it('ohne eigenen spez. Ertrag keine Abweichung in der Summary', () => {
    const v = { anzahl_anlagen: 5, spez_ertrag: { median: 131 } } as unknown as MonatsVergleich
    expect(communityBlock(v, d, 'Mai', 2026)!.summary).not.toMatch(/spez\. Ertrag/)
  })
})
