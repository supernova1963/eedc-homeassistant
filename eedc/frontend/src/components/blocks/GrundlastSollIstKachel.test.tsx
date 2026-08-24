import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { GrundlastSollIstKachel, MonatsprognoseKachel } from './GrundlastSollIstKachel'
import { baueJahrAlsMonat } from '../../v4/JahrAggregat'
import type { AktuellerMonatResponse } from '../../api/aktuellerMonat'
import { aktuellerMonat } from '../../test/factories'

const d = (over: Partial<AktuellerMonatResponse> = {}) =>
  aktuellerMonat(2026, 8, {
    pv_erzeugung_kwh: 400, gesamtverbrauch_kwh: 1460, soll_pv_kwh: 450,
    ...over,
  })

describe('GrundlastSollIstKachel', () => {
  it('zeigt Grundlast absolut (W, wie Live) + Anteil, wenn Stundendaten da sind', () => {
    render(<GrundlastSollIstKachel d={d({ grundlast_kw: 0.38, grundlast_kwh: 270, grundlast_anteil_prozent: 18.5 })} />)
    expect(screen.getByText('380 W')).toBeInTheDocument()       // 0,38 kW → 380 W
    expect(screen.getByText(/18,5 %/)).toBeInTheDocument()
    expect(screen.queryByText(/PVGIS/)).not.toBeInTheDocument() // PVGIS verdrängt
  })

  it('fällt auf PVGIS-SOLL/IST zurück, wenn keine Stundendaten (grundlast_kw null)', () => {
    render(<GrundlastSollIstKachel d={d({ grundlast_kw: null, pv_erzeugung_kwh: 400, soll_pv_kwh: 450 })} />)
    expect(screen.getByText('IST/SOLL (PVGIS)')).toBeInTheDocument()
    expect(screen.getByText('89 %')).toBeInTheDocument()        // 400 / 450
  })

  it('zeigt Leer-Hinweis, wenn weder Grundlast noch PVGIS vorliegen', () => {
    render(<GrundlastSollIstKachel d={d({ grundlast_kw: null, soll_pv_kwh: null })} />)
    expect(screen.getByText(/Keine Grundlast- oder PVGIS-Daten/)).toBeInTheDocument()
  })
})

describe('MonatsprognoseKachel (Melder dietmar1968, T89667 #155)', () => {
  // Der laufende Monat: 4 von 31 Tagen, SOLL bis heute 179,1 kWh, volle
  // Monatsprognose 1387,9 kWh, IST 264,75 kWh.
  const laufend = (over: Partial<AktuellerMonatResponse> = {}) => d({
    pv_erzeugung_kwh: 264.75, soll_pv_kwh: 179.1, soll_pv_kwh_monat: 1387.9,
    soll_pv_tage: 4, soll_pv_tage_gesamt: 31, ...over,
  })

  it('zeigt den Fortschritt gegen den GANZEN Monat und benennt ihn', () => {
    render(<MonatsprognoseKachel d={laufend()} />)
    expect(screen.getByText('Monatsprognose (PVGIS)')).toBeInTheDocument()
    expect(screen.getByText('19 %')).toBeInTheDocument()          // 264,75 / 1387,9
    expect(screen.getByText(/von 1\.388 kWh · ganzer Monat/)).toBeInTheDocument()
    expect(screen.getByText(/Tag 4 von 31/)).toBeInTheDocument()
  })

  it('erscheint auch dann, wenn die SOLL-Kachel daneben verdrängt ist', () => {
    // Mit Stundendaten zeigt GrundlastSollIstKachel die Grundlast — ohne diese
    // Kachel hätte die Anlage gar keine Einordnung des laufenden Monats mehr.
    const mitStunden = laufend({ grundlast_kw: 0.38, grundlast_anteil_prozent: 18.5 })
    render(<MonatsprognoseKachel d={mitStunden} />)
    expect(screen.getByText('19 %')).toBeInTheDocument()
  })

  it('schweigt im abgeschlossenen Monat und ohne Prognose', () => {
    const { container: fertig } = render(<MonatsprognoseKachel d={d({
      pv_erzeugung_kwh: 1843.25, soll_pv_kwh: 1509, soll_pv_kwh_monat: 1509,
      soll_pv_tage: 31, soll_pv_tage_gesamt: 31,
    })} />)
    expect(fertig).toBeEmptyDOMElement()
    const { container: ohne } = render(<MonatsprognoseKachel d={d({ soll_pv_kwh: null })} />)
    expect(ohne).toBeEmptyDOMElement()
  })
})

describe('baueJahrAlsMonat — Grundlast-Aggregation (R12-1)', () => {
  it('summiert grundlast_kwh additiv, Anteil nur über Monate MIT Grundlast-Daten', () => {
    const monate = [
      d({ jahr: 2026, monat: 1, grundlast_kw: 0.4, grundlast_kwh: 288, gesamtverbrauch_kwh: 1000 }),
      d({ jahr: 2026, monat: 2, grundlast_kw: 0.5, grundlast_kwh: 372, gesamtverbrauch_kwh: 900 }),
      // Monat ohne Stundendaten — fließt NICHT in den Anteils-Nenner ein:
      d({ jahr: 2026, monat: 3, grundlast_kw: null, grundlast_kwh: null, gesamtverbrauch_kwh: 500 }),
    ]
    const jahr = baueJahrAlsMonat(monate, 2026)
    expect(jahr.grundlast_kwh).toBe(660)                  // 288 + 372 (null ignoriert)
    expect(jahr.grundlast_kw).toBeCloseTo(0.45, 2)        // Ø der Monats-Mediane (0,4 / 0,5)
    expect(jahr.grundlast_anteil_prozent).toBeCloseTo(34.7, 1) // 660 / 1900 (nur Monate 1+2)
  })

  it('ohne jegliche Grundlast-Daten → alle Grundlast-Felder null', () => {
    const monate = [d({ jahr: 2026, monat: 1, grundlast_kw: null, grundlast_kwh: null })]
    const jahr = baueJahrAlsMonat(monate, 2026)
    expect(jahr.grundlast_kwh).toBeNull()
    expect(jahr.grundlast_anteil_prozent).toBeNull()
  })
})
