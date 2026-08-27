/**
 * DatenquellenZuordnung — „Weitere Größen erfassen" muss sich AUFKLAPPEN LASSEN.
 *
 * Der Fehler, den diese Datei festhält (F-65, gemeldet von **pipp086** im Forum
 * simon42 T89667 #224, am Tag der v4.0.29-Auslieferung): Der Abschnitt ließ sich
 * anklicken und passierte nichts.
 *
 * Ursache war keine Logik im Abschnitt selbst, sondern die Deps-Liste des
 * `useMemo`, das die Blöcke baut. `offeneErweiterung` kam einen Tag zuvor dazu
 * (`cf3b0a16`), stand aber nicht in der Liste — der Klick setzte den Zustand, das
 * Memo rechnete nicht neu, und die eingefrorene render-Closure zeigte weiter den
 * alten. Das `eslint-disable react-hooks/exhaustive-deps` an derselben Stelle
 * unterdrückte genau die Warnung, die es gemeldet hätte, und kann dort nicht
 * entfallen (die Regel verlangt zwei bei jedem Render neu gebaute Funktionen,
 * deren Aufnahme das Memo wirkungslos machte — am 27.08. gemessen).
 *
 * ⭐ Deshalb prüft diese Datei das **Verhalten**, nicht die Deps-Liste: Ein Test,
 * der die Liste liest, prüft die Schreibweise der Erinnerung; ein Test, der
 * klickt, prüft, was der Anwender erlebt. Er meldet rot bei JEDEM künftigen
 * Einfrieren dieses Abschnitts, unabhängig von der Ursache.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import DatenquellenZuordnung from './DatenquellenZuordnung'

// Die Factory wird gehoistet — die Fixture muss darin entstehen.
vi.mock('../../api/datenquellen', () => {
  const basisFeld = {
    id: 'basis.pv_gesamt_kwh', feld: 'pv_gesamt_kwh', typ: 'basis',
    label: 'PV-Erzeugung Zählerstand', einheit: 'kWh', kategorie: 'energy',
    hinweis: '', standard_topic: 'eedc/1/energy/pv_gesamt_kwh',
    quelle: 'keine', gateway_topic: null, bedarf: 'pflicht',
    ha_entity: null, ha_name: null,
    invertieren: false, wert: null, wert_zeit: null, probleme: [],
  }
  // Die vierte Stufe (R1): untypisch an diesem Gerät, deshalb zugeklappt.
  // Der Kühlzähler an einer Heizungs-Wärmepumpe ist genau MartyBrs und
  // pipp086s Fall — der, für den v4.0.29 die Stufe gebaut hat.
  const erweitertesFeld = {
    ...basisFeld,
    id: 'basis.kuehlung_kwh', feld: 'kuehlung_kwh',
    label: 'Kältemenge Kühlen', bedarf: 'optional',
    standard_topic: 'eedc/1/energy/kuehlung_kwh',
    erweitert: true,
  }
  return {
    VERBINDUNG_GEAENDERT_EVENT: 'eedc:verbindung-geaendert',
    datenquellenApi: {
      getFelder: vi.fn(() => Promise.resolve({
        gruppen: [{
          id: 'basis', label: 'Anlage (Basis)', typ: 'basis',
          felder: [basisFeld, erweitertesFeld],
        }],
        verfuegbarkeit: { ha: true, mqtt: false, ha_quelle: 'ha_app' },
      })),
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
  useSelectedAnlage: () => ({ selectedAnlageId: 1, selectedAnlage: { id: 1, anlagenname: 'Test' } }),
}))

describe('DatenquellenZuordnung — „Weitere Größen erfassen" (F-65)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('klappt den Abschnitt beim Klick auf und wieder zu', async () => {
    render(<DatenquellenZuordnung />)

    const schalter = await screen.findByRole('button', { name: /Weitere Größen erfassen/i })
    // Zugeklappt ist der Default — die Fläche soll kurz bleiben (R1).
    expect(schalter).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText(/Kältemenge Kühlen/)).not.toBeInTheDocument()

    fireEvent.click(schalter)

    // ⛔ Genau hier stand pipp086s Fehler: der Zustand kippte, die Anzeige nicht.
    expect(schalter).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText(/Kältemenge Kühlen/)).toBeInTheDocument()

    // Und zurück — ein Schalter, der nur in eine Richtung wirkt, ist keiner.
    fireEvent.click(schalter)
    expect(schalter).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText(/Kältemenge Kühlen/)).not.toBeInTheDocument()
  })

  it('zählt die verborgenen Felder im Schalter mit', async () => {
    render(<DatenquellenZuordnung />)
    // Ohne die Zahl wäre nicht erkennbar, dass sich das Aufklappen lohnt.
    expect(await screen.findByRole('button', { name: /Weitere Größen erfassen \(1\)/i }))
      .toBeInTheDocument()
  })

  it('lässt das gewöhnliche Feld daneben unberührt sichtbar', async () => {
    render(<DatenquellenZuordnung />)
    // Gegenprobe zur ersten Behauptung: „nicht im Dokument" muss am erweiterten
    // Feld liegen, nicht daran, dass die Fläche überhaupt nichts rendert.
    expect(await screen.findByText(/PV-Erzeugung Zählerstand/)).toBeInTheDocument()
  })
})
