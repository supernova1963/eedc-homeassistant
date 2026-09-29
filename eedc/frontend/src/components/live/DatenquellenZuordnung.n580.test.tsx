/**
 * N-580 — die Zusammenfassung eines Geräte-Blocks zählt in Einzahl, wenn genau
 * ein Feld offen ist.
 *
 * Gefunden im Galerie-Bild `einstellungen_datenquellen.png` (28.09.2026): an
 * der Wärmepumpe stand **„1 Felder noch ohne Quelle"**. Unmittelbar daneben,
 * in derselben Zeile, war die Regel für das Gerät längst angewandt
 * (`… === 1 ? 'Gerät' : 'Geräte'`) — beim Feld war sie vergessen. Genau diese
 * Nachbarschaft macht den Fall zur Klasse und nicht zum Tippfehler; die
 * baumweite Erhebung fand 65 solche Stellen, die Zentrale steht seither in
 * `lib/plural.ts`.
 *
 * ⚠ Geprüft wird die **Zusammenfassung in der Blockkopfzeile**, nicht der Text
 * im aufgeklappten Block — dort entsteht die Zeichenkette (`summary`).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import DatenquellenZuordnung from './DatenquellenZuordnung'

/** Wie viele Pflichtfelder ohne Quelle die Fixture liefert — je Test gesetzt. */
const lage = vi.hoisted(() => ({ offen: 1 }))

vi.mock('../../api/datenquellen', () => {
  const feld = (n: number, offen: boolean) => ({
    id: `inv_live_7_f${n}`, feld: `f${n}`, typ: 'waermepumpe',
    label: `Feld ${n}`, einheit: 'W', kategorie: 'live',
    hinweis: '', standard_topic: '',
    // `offenePflichten` zählt genau diese Kombination: Pflicht UND ohne Quelle.
    quelle: offen ? 'keine' : 'ha_app',
    bedarf: 'pflicht',
    gateway_topic: null, ha_entity: offen ? null : 'sensor.x', ha_name: null,
    invertieren: false, wert: null, wert_zeit: null, probleme: [],
  })
  return {
    VERBINDUNG_GEAENDERT_EVENT: 'eedc:verbindung-geaendert',
    datenquellenApi: {
      getFelder: vi.fn(() => Promise.resolve({
        gruppen: [{
          id: 'inv:7', titel: 'Daikin Altherma', typ: 'waermepumpe',
          // Immer vier Felder; nur wie viele davon offen sind, wechselt.
          felder: [0, 1, 2, 3].map((n) => feld(n, n < lage.offen)),
        }],
        verfuegbarkeit: { ha: true, mqtt: false, ha_quelle: 'ha_app' },
      })),
      setQuelle: vi.fn(() => Promise.resolve()),
      setInvert: vi.fn(() => Promise.resolve()),
      haSensoren: vi.fn(() => Promise.resolve({ sensoren: [], vorschlaege: [], integrationen: [], warnungen: {} })),
      taktCheck: vi.fn(() => Promise.resolve({ geprueft: false })),
    },
  }
})

vi.mock('../../hooks', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useSelectedAnlage: () => ({ selectedAnlageId: 1, selectedAnlage: { id: 1, anlagenname: 'Test' } }),
}))

describe('N-580 — Einzahl in der Blockzusammenfassung', () => {
  beforeEach(() => { lage.offen = 1 })

  it('DER KERN: ein offenes Feld heißt „1 Feld noch ohne Quelle"', async () => {
    lage.offen = 1
    render(<DatenquellenZuordnung />)

    expect(await screen.findByText(/1 Feld noch ohne Quelle/)).toBeInTheDocument()
    // Die Gegenrichtung gehört dazu: „1 Felder" darf nirgends stehen.
    expect(screen.queryByText(/1 Felder/)).toBeNull()
  })

  it('zwei offene Felder heißen weiter „2 Felder noch ohne Quelle"', async () => {
    lage.offen = 2
    render(<DatenquellenZuordnung />)

    expect(await screen.findByText(/2 Felder noch ohne Quelle/)).toBeInTheDocument()
  })

  it('das Gerät selbst zählt unverändert in Einzahl', async () => {
    render(<DatenquellenZuordnung />)

    // Eine Gruppe ⇒ „1 Gerät"; diese Hälfte war schon vor N-580 richtig und
    // darf beim Umbau auf die Zentrale nicht verloren gehen.
    expect(await screen.findByText(/1 Gerät ·/)).toBeInTheDocument()
  })
})
