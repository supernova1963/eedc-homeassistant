/**
 * Block ④ „Verlauf" kennzeichnet gerechnete Modul-Werte (A3/a1).
 *
 * Anlass Rainer/rapahl (PN 2026-07-25): der PV-Hub zeigt im Verlauf Balken je
 * Modul, die anteilig nach kWp aus der Anlagen-Erzeugung gerechnet sind —
 * während Block ⑤ dieselben Module gemessen zeigt. Beide Stellen von Block ④
 * (Chart-Kopf und Verteilungsbalken) müssen das ausweisen.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { geraetBloecke } from './KomponentenTypV4'
import type { ParkApi } from '../components/park'
import type { KompGeraet } from './komponentenAdapter'
import type { Investition } from '../types'

const NICHTS_GEPARKT: ParkApi = {
  aktiv: false, istGeparkt: () => false, park: () => {}, entparke: () => {}, zuruecksetzen: () => {},
  geparkt: [], registriere: () => () => {}, parkbareAnzahl: 0,
}

const HERKUNFT = {
  zustand: 'geschaetzt' as const,
  quelleLabel: 'kWp-Anteil',
  bezug: 'Erzeugung je Modul',
  hinweis: 'Werte je Modul sind nicht gemessen, sondern anteilig nach kWp verteilt. '
    + 'Die gemessenen Werte je String stehen im Block „Vergleich".',
}

function geraet(mitHerkunft: boolean): KompGeraet {
  return {
    inv: { id: 0, anlage_id: 1, typ: 'pv-module', bezeichnung: 'PV-Anlage', aktiv: true } as Investition,
    label: 'PV-Anlage',
    status: [],
    verlauf: {
      bars: [{ key: 'm11', label: 'Süd', farbe: 'bg-red-500', stapel: 'erz' }],
      rows: [{ name: '2025', m11: 600 }],
      gestapelt: true,
      herkunft: mitHerkunft ? HERKUNFT : undefined,
      verteilungen: [
        { titel: 'Erzeugung nach Modul', herkunft: mitHerkunft ? HERKUNFT : undefined,
          segmente: [{ label: 'Süd', wert: 600, farbe: 'bg-red-500' }] },
        { titel: 'Verwendung der Erzeugung',
          segmente: [{ label: 'Direktverbrauch', wert: 400, farbe: 'bg-green-500' }] },
      ],
    },
  }
}

function verlaufBlock(mitHerkunft: boolean) {
  const bloecke = geraetBloecke(geraet(mitHerkunft), 'pv-module', 1, NICHTS_GEPARKT, {}, () => {})
  const block = bloecke.find((b) => b.id === 'verlauf')
  if (!block) throw new Error('Verlauf-Block fehlt')
  return block
}

describe('Block ④ Verlauf — Herkunft der Modul-Werte', () => {
  it('kennzeichnet Chart-Kopf UND Verteilungsbalken als gerechnet', () => {
    render(<>{verlaufBlock(true).render(false)}</>)
    // Beide Stellen tragen dasselbe SoT-Badge (iconOnly, aria-label aus ZUSTAND_META)
    expect(screen.getAllByLabelText('geschätzt (kWp-Anteil)')).toHaveLength(2)
    // Chart-Kopf sagt, WORAUF sich die Kennzeichnung bezieht (Verwendung ist gemessen)
    expect(screen.getByText('Erzeugung je Modul')).toBeInTheDocument()
    // Erklärsatz sichtbar (nicht nur Hover) inkl. Verweis auf Block ⑤
    const saetze = screen.getAllByText(/anteilig nach kWp verteilt/)
    expect(saetze.length).toBe(2)
    expect(saetze[0].textContent).toContain('Vergleich')
  })

  it('ohne Herkunft bleibt der Block unmarkiert (andere Typen unverändert)', () => {
    render(<>{verlaufBlock(false).render(false)}</>)
    expect(screen.queryByLabelText(/geschätzt/)).not.toBeInTheDocument()
    expect(screen.queryByText(/anteilig nach kWp/)).not.toBeInTheDocument()
  })
})
