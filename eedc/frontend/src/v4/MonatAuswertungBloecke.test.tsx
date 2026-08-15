import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { baueMonatAuswertungBloecke } from './MonatAuswertungBloecke'
import { NOOP_PARK, type ParkApi } from '../components/park'
import type { MonatsAuswertung } from '../api/energie_profil'

// Voll-Fixture; einzelne Felder je Test überschrieben.
function a(over: Partial<MonatsAuswertung> = {}): MonatsAuswertung {
  return {
    jahr: 2026, monat: 5, tage_im_monat: 31, tage_mit_daten: 28,
    pv_kwh: 412, verbrauch_kwh: 366, einspeisung_kwh: 189, netzbezug_kwh: 143,
    ueberschuss_kwh: 50, defizit_kwh: 20,
    autarkie_prozent: 61, eigenverbrauch_prozent: 54,
    performance_ratio_avg: 0.84, batterie_vollzyklen_summe: 12.3,
    grundbedarf_kw: 0.3, batterie_ladung_kwh: 90, batterie_entladung_kwh: 80,
    batterie_wirkungsgrad: 0.9, direkt_eigenverbrauch_kwh: 140,
    pv_tag_best_kwh: 30, pv_tag_schnitt_kwh: 15, pv_tag_schlecht_kwh: 2,
    typisches_tagesprofil: [
      { stunde: 12, pv_kw: 3.1, verbrauch_kw: 0.8 },
      { stunde: 13, pv_kw: 3.4, verbrauch_kw: 0.9 },
    ],
    kategorien: [
      { kategorie: 'pv_module', kwh: 400, anteil_prozent: 97 },
      { kategorie: 'bkw', kwh: 12, anteil_prozent: 3 },
      { kategorie: 'waermepumpe', kwh: 120, anteil_prozent: 33 },
      { kategorie: 'haushalt', kwh: 200, anteil_prozent: 55 },
    ],
    komponenten: [],
    peak_netzbezug: [{ datum: '2026-05-10', stunde: 19, wert_kw: 4.2 }],
    peak_einspeisung: [{ datum: '2026-05-15', stunde: 12, wert_kw: 6.8 }],
    peak_pv: null,
    heatmap: [],
    boersenpreis_avg_cent: 8.4,
    negative_preis_stunden: 3,
    einspeisung_neg_preis_kwh: 5.5,
    ...over,
  }
}

/** ParkApi, in der die gegebenen IDs als geparkt gelten. */
function parkMit(...geparkt: string[]): ParkApi {
  return { ...NOOP_PARK, aktiv: true, istGeparkt: (id) => geparkt.includes(id) }
}

describe('baueMonatAuswertungBloecke — Block-Auswahl', () => {
  it('baut alle vier Blöcke, wenn Daten da sind und nichts geparkt ist', () => {
    const ids = baueMonatAuswertungBloecke(a(), NOOP_PARK).map((b) => b.id)
    expect(ids).toEqual(['kategorien', 'tagesprofil', 'peaks', 'negativpreis'])
  })

  it('Kategorien-Block entfällt ohne Kategorie-Daten', () => {
    const ids = baueMonatAuswertungBloecke(a({ kategorien: [] }), NOOP_PARK).map((b) => b.id)
    expect(ids).not.toContain('kategorien')
  })

  it('Tagesprofil-Block entfällt ohne Profil-Daten', () => {
    const ids = baueMonatAuswertungBloecke(a({ typisches_tagesprofil: [] }), NOOP_PARK).map((b) => b.id)
    expect(ids).not.toContain('tagesprofil')
  })

  it('§51-Block nur bei negativen Preisstunden > 0', () => {
    expect(baueMonatAuswertungBloecke(a({ negative_preis_stunden: 0 }), NOOP_PARK).map((b) => b.id)).not.toContain('negativpreis')
    expect(baueMonatAuswertungBloecke(a({ negative_preis_stunden: null }), NOOP_PARK).map((b) => b.id)).not.toContain('negativpreis')
  })

  it('Peaks-Block entfällt, wenn beide Peak-Listen leer sind', () => {
    const ids = baueMonatAuswertungBloecke(a({ peak_netzbezug: [], peak_einspeisung: [] }), NOOP_PARK).map((b) => b.id)
    expect(ids).not.toContain('peaks')
  })

  it('Peaks-Block bleibt, solange EINE Liste Daten hat', () => {
    const ids = baueMonatAuswertungBloecke(a({ peak_netzbezug: [] }), NOOP_PARK).map((b) => b.id)
    expect(ids).toContain('peaks')
  })

  it('Element-Park-Doktrin: Block entfällt, wenn sein einziges Element geparkt ist', () => {
    expect(baueMonatAuswertungBloecke(a(), parkMit('el:tagesprofil')).map((b) => b.id)).not.toContain('tagesprofil')
  })

  // Bis 2026-08-15 lag EINE Parkbar über beiden Balken — wer den Verbrauch
  // wegräumen wollte, verlor die Erzeugung mit. Jetzt wie bei den Peaks zwei.
  it('Kategorien: jeder Balken einzeln parkbar, Block erst mit beiden weg', () => {
    const nurErz = baueMonatAuswertungBloecke(a(), parkMit('el:kategorien-verbrauch')).map((b) => b.id)
    expect(nurErz).toContain('kategorien')
    const nurVerb = baueMonatAuswertungBloecke(a(), parkMit('el:kategorien-erzeugung')).map((b) => b.id)
    expect(nurVerb).toContain('kategorien')
    const beide = baueMonatAuswertungBloecke(
      a(), parkMit('el:kategorien-erzeugung', 'el:kategorien-verbrauch'),
    ).map((b) => b.id)
    expect(beide).not.toContain('kategorien')
  })

  it('Peaks entfällt erst, wenn BEIDE Listen geparkt sind', () => {
    expect(baueMonatAuswertungBloecke(a(), parkMit('el:peak-netzbezug')).map((b) => b.id)).toContain('peaks')
    expect(baueMonatAuswertungBloecke(a(), parkMit('el:peak-netzbezug', 'el:peak-einspeisung')).map((b) => b.id)).not.toContain('peaks')
  })

  it('§51 entfällt erst, wenn alle drei KPIs geparkt sind', () => {
    expect(baueMonatAuswertungBloecke(a(), parkMit('kpi:51-stunden', 'kpi:51-einspeisung')).map((b) => b.id)).toContain('negativpreis')
    expect(baueMonatAuswertungBloecke(a(), parkMit('kpi:51-stunden', 'kpi:51-einspeisung', 'kpi:51-boersenpreis')).map((b) => b.id)).not.toContain('negativpreis')
  })
})

describe('baueMonatAuswertungBloecke — Render (jsdom-fähige Blöcke)', () => {
  const bloecke = baueMonatAuswertungBloecke(a(), NOOP_PARK)
  const render1 = (id: string) => render(<>{bloecke.find((b) => b.id === id)!.render(false)}</>)

  it('Peaks: Datum (TT.MM.), Stunde und Wert (de-DE)', () => {
    render1('peaks')
    expect(screen.getByText('Top Netzbezug-Stunden')).toBeInTheDocument()
    expect(screen.getByText('10.05.')).toBeInTheDocument()
    expect(screen.getByText('19:00')).toBeInTheDocument()
    expect(screen.getByText('4,2 kW')).toBeInTheDocument()
  })

  it('Kategorien: Erzeuger- und Verbraucher-Labels aus der SoT-Map', () => {
    render1('kategorien')
    expect(screen.getByText('Erzeugung nach Kategorie')).toBeInTheDocument()
    expect(screen.getByText('PV-Module')).toBeInTheDocument()
    expect(screen.getByText('Verbrauch nach Kategorie')).toBeInTheDocument()
    expect(screen.getByText('Wärmepumpe')).toBeInTheDocument()
    expect(screen.getByText('Haushalt')).toBeInTheDocument()
  })

  it('§51: die drei KPI-Kacheln', () => {
    render1('negativpreis')
    expect(screen.getByText('Neg. Börsenpreis')).toBeInTheDocument()
    expect(screen.getByText('Einspeisung bei neg. Preis')).toBeInTheDocument()
    expect(screen.getByText('Börsenpreis Ø')).toBeInTheDocument()
  })
})
