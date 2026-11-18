/**
 * **R-A (WK-16f, Prinzip F-7)** — die Fläche sagt, wo ein zugeordneter Wert
 * ausgewertet wird.
 *
 * Gernot, 14.09.2026: *„Bitte achte auch darauf, dass alle zugeordneten
 * Sensoren in mindestens einer Auswertung verarbeitet werden, da man sich
 * anderenfalls die Frage stellt, wofür habe ich diesen Sensor zugeordnet."*
 *
 * Drei Dinge hält diese Datei fest:
 *
 * ⭐ **Der Satz steht am Feld**, im selben leisen Ton wie der Hinweis darüber
 * (Konzept §9: *„Hinweis am Feld, kein Alarm"*) — kein neuer Stil, keine
 * eigene Farbe, kein Warnsymbol.
 *
 * ⛔ **Kein Satz ohne Inhalt.** Ein Feld ohne Auswertung bekommt **kein**
 * „Ausgewertet in: —". Das wäre ein Satz, der die Frage stellt, die er
 * beantworten soll.
 *
 * ⚠ **Der Client hält keine Tabelle.** Die Wegbeschreibungen kommen fertig aus
 * `core/feld_auswertungen.py`; eine zweite Liste hier wäre die Drift, an der
 * `FeldProblem.art` schon einmal auseinandergelaufen ist (N-35/N-40).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import DatenquellenZuordnung from './DatenquellenZuordnung'

vi.mock('../../api/datenquellen', () => {
  const basis = {
    id: 'basis_energy_netzbezug_kwh', feld: 'netzbezug_kwh', typ: 'basis',
    label: 'Netzbezug Zählerstand', einheit: 'kWh', kategorie: 'energy',
    hinweis: '', standard_topic: 'eedc/1_Test/energy/netzbezug_kwh',
    quelle: 'ha_app', gateway_topic: null,
    ha_entity: 'sensor.netz', ha_name: 'Netzbezug',
    invertieren: false, wert: 42, wert_zeit: null, probleme: [],
    bedarf: 'optional', bedarf_grund: null, bedarf_text: null,
    ausgewertet_in: ['Cockpit → Monat', 'Cockpit → Jahr', 'HA-Sensoren'],
  }
  // Die Gegenprobe: dasselbe Feld-Gerüst, **ohne** Auswertung.
  const stumm = {
    ...basis,
    id: 'basis_energy_ohne_kwh', feld: 'ohne_auswertung_kwh',
    label: 'Feld ohne Auswertung', ausgewertet_in: [],
  }
  return {
    VERBINDUNG_GEAENDERT_EVENT: 'eedc:verbindung-geaendert',
    datenquellenApi: {
      getFelder: vi.fn(() => Promise.resolve({
        gruppen: [{
          id: 'basis', titel: 'Anlage (Basis)', typ: 'basis',
          felder: [basis, stumm],
        }],
        verfuegbarkeit: { ha: true, mqtt: false, ha_quelle: 'ha_app' },
      })),
      pruefeQuelle: vi.fn(() => Promise.resolve({ grund_erforderlich: false })),
      korrekturLaeufe: vi.fn(() => Promise.resolve([])),
      setQuelle: vi.fn(() => Promise.resolve()),
      setInvert: vi.fn(() => Promise.resolve()),
      haSensoren: vi.fn(() => Promise.resolve({
        sensoren: [], vorschlaege: [], integrationen: [], warnungen: {},
      })),
      taktCheck: vi.fn(() => Promise.resolve({ geprueft: false })),
    },
  }
})

vi.mock('../../hooks', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useSelectedAnlage: () => ({
    selectedAnlageId: 1, selectedAnlage: { id: 1, anlagenname: 'Test' },
  }),
}))

/**
 * ⚠ **Der Basis-Block ist offen** (`defaultOpen: istBasis`), der Hinweis-Block
 * am Feld aber zugeklappt. Er geht über den Info-Knopf auf — und genau dessen
 * Bedingung ist Teil dessen, was hier gemessen wird: Ohne `hinweis`-Text gab es
 * den Knopf bis zum 14.09.2026 gar nicht.
 */
async function oeffneHinweis(label: RegExp) {
  render(<DatenquellenZuordnung />)
  const zeile = (await screen.findByText(label)).closest('div')?.parentElement
  const knopf = zeile?.querySelector('button[aria-label="Hinweis anzeigen"]')
  return { zeile, knopf }
}

describe('R-A — „Ausgewertet in" auf der Zuordnungs-Fläche', () => {
  it('nennt die Sichten, in denen der Wert erscheint', async () => {
    const { knopf } = await oeffneHinweis(/Netzbezug Zählerstand/)
    expect(knopf).not.toBeNull()
    fireEvent.click(knopf as HTMLElement)

    const satz = await screen.findByText(/Cockpit → Monat · Cockpit → Jahr · HA-Sensoren/)
    expect(satz).toBeInTheDocument()
    expect(satz.textContent).toContain('Ausgewertet in:')
  })

  it('DIE GEGENPROBE: ohne Auswertung steht kein Satz da', async () => {
    // ⭐ Ohne diese Zeile hielte die Probe darüber nur fest, dass **irgendein**
    // Text gerendert wird — nicht, dass er aus `ausgewertet_in` stammt.
    const { knopf } = await oeffneHinweis(/Feld ohne Auswertung/)
    expect(knopf).toBeNull()

    render(<DatenquellenZuordnung />)
    expect(screen.queryAllByText(/Ausgewertet in:.*—/)).toHaveLength(0)
  })

  it('trägt den leisen Ton der Fläche — keine Warnfarbe, kein Symbol', async () => {
    const { knopf } = await oeffneHinweis(/Netzbezug Zählerstand/)
    fireEvent.click(knopf as HTMLElement)
    const satz = await screen.findByText(/Cockpit → Monat · Cockpit → Jahr/)

    expect(satz.className).toContain('text-gray-500')
    expect(satz.className).not.toContain('amber')
    expect(satz.className).not.toContain('red')
    expect(satz.querySelector('svg')).toBeNull()
  })
})
