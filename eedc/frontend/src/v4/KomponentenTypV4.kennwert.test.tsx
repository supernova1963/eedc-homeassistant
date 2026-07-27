/**
 * Block ⑦ „Einstellungen" zeigt die EFFEKTIVE Nennleistung (A26/N106).
 *
 * Anlass: Wer seine kWp nur im `parameter`-JSON gepflegt hat (Import-/
 * Altbestand, #229), hatte in der Rohspalte `leistung_kwp` nichts stehen — die
 * Zeile „Leistung … kWp" fehlte im Komponenten-Hub komplett, obwohl der Wert
 * gepflegt war. Der Server liefert seit A26 zusätzlich
 * `leistung_kwp_effektiv`; diese Tests pinnen, dass die ANZEIGE es liest.
 *
 * Gegenprobe im selben File: die Rohspalte allein darf die Zeile NICHT mehr
 * erzeugen — sonst wäre die Umstellung nur additiv und der alte Pfad bliebe
 * still bestehen.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'

const getFelder = vi.fn()
vi.mock('../api/datenquellen', () => ({ datenquellenApi: { getFelder: (...a: unknown[]) => getFelder(...a) } }))

import { geraetBloecke } from './KomponentenTypV4'
import { ParkProvider } from '../components/park'
import type { ParkApi } from '../components/park'
import type { KompGeraet } from './komponentenAdapter'
import type { Investition } from '../types'

const NICHTS_GEPARKT: ParkApi = {
  aktiv: false, istGeparkt: () => false, park: () => {}, entparke: () => {}, zuruecksetzen: () => {},
  geparkt: [], registriere: () => () => {}, parkbareAnzahl: 0,
}

const modul = (over: Partial<Investition>): Investition => ({
  id: 11, anlage_id: 1, typ: 'pv-module', bezeichnung: 'Dach Süd', aktiv: true, ...over,
} as Investition)

/** Rendert Block ⑦ und wartet den Datenquellen-Fetch ab (sonst act()-Warnung). */
async function zeigeEinstellungen(inv: Investition) {
  const g: KompGeraet = { inv, label: inv.bezeichnung, status: [], verknuepfteInvs: [inv] }
  const block = geraetBloecke(g, 'pv-module', 1, NICHTS_GEPARKT, {}, () => {}).find((b) => b.id === 'einstellungen')
  if (!block) throw new Error('Einstellungen-Block fehlt')
  render(<ParkProvider persistKey="test:kennwert">{block.render(false)}</ParkProvider>)
  await screen.findByText('Keine Datenquellen zugeordnet.')
}

beforeEach(() => {
  vi.clearAllMocks()
  getFelder.mockResolvedValue({ gruppen: [] })
})

describe('Komponenten-Hub ⑦ — Nennleistung an der API-Grenze', () => {
  it('#229: kWp nur im parameter-JSON ⇒ die Zeile erscheint mit dem effektiven Wert', async () => {
    await zeigeEinstellungen(modul({
      leistung_kwp: undefined,          // Rohspalte leer — der Altbestand-Fall
      leistung_kwp_effektiv: 8.4,       // vom Server aus parameter.kwp geheilt
      parameter: { kwp: 8.4 },
    }))

    expect(screen.getByText('Leistung')).toBeInTheDocument()
    expect(screen.getByText('8,4 kWp')).toBeInTheDocument()
  })

  it('Normalfall: gepflegte Spalte ⇒ unveränderte Anzeige', async () => {
    await zeigeEinstellungen(modul({ leistung_kwp: 6, leistung_kwp_effektiv: 6 }))

    expect(screen.getByText('6,0 kWp')).toBeInTheDocument()
  })

  it('Gegenprobe: die Rohspalte allein erzeugt die Zeile NICHT mehr', async () => {
    // Kann real nicht vorkommen (der Server füllt beide Felder) — der Test
    // prüft, dass die Anzeige-Stelle wirklich umgestellt ist und nicht nur
    // zusätzlich auf das neue Feld schaut.
    await zeigeEinstellungen(modul({ leistung_kwp: 6, leistung_kwp_effektiv: undefined }))

    expect(screen.queryByText('Leistung')).not.toBeInTheDocument()
  })

  it('ohne jede Nennleistung bleibt die Zeile weg (keine 0,0 kWp)', async () => {
    await zeigeEinstellungen(modul({ leistung_kwp: undefined, leistung_kwp_effektiv: null }))

    expect(screen.queryByText('Leistung')).not.toBeInTheDocument()
    expect(screen.queryByText(/kWp/)).not.toBeInTheDocument()
  })
})
