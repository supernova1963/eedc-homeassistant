/**
 * MappingTabelle — die Zuordnungs-Fläche zeigt den Erklärtext des gewählten
 * Zielfelds.
 *
 * Schwesterprobe im Backend: `test_custom_import_feld_hinweis.py` (dort wird
 * geprüft, dass der Hinweis die Auswahl überhaupt *erreicht*). Hier geht es
 * allein darum, dass er **angezeigt** wird — beide Hälften sind nötig, eine
 * gelieferte und nie gerenderte Angabe hilft niemandem.
 *
 * Der Fall dahinter: Ein Melder ordnete eine Umgebungswärme-Spalte auf ein
 * Wärmemengen-Feld zu, weil die Option nur „WP: <Gerät> – Warmwasser (kWh)"
 * sagte. Dass dort eine *thermische* Größe erwartet wird, stand nur in einem
 * Hinweis, den diese Fläche nicht anzeigte.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import MappingTabelle from './MappingTabelle'
import type { AnalyzeResult } from '../../../api/customImport'

const HINWEIS_THERMISCH = 'Abgegebene Warmwasser-Wärme (thermisch) in kWh.'
const HINWEIS_ELEKTRISCH = 'Elektrische Energie für die Warmwasserbereitung.'

function analyse(): AnalyzeResult {
  return {
    spalten: [
      { name: 'Produzierte Waerme WW', sample_values: ['142', '158', '133'] },
      { name: 'Verbrauchte Energie WW', sample_values: ['54,9', '96', '83'] },
    ],
    investitions_felder: [
      {
        id: 'inv:42:warmwasser_kwh',
        label: 'WP: Nibe – Warmwasser-Wärme (kWh)',
        required: false,
        group: 'inv_wp',
        hinweis: HINWEIS_THERMISCH,
      },
      {
        id: 'inv:42:strom_warmwasser_kwh',
        label: 'WP: Nibe – Strom Warmwasser (kWh)',
        required: false,
        group: 'inv_wp',
        hinweis: HINWEIS_ELEKTRISCH,
      },
      {
        id: 'inv:42:km_gefahren',
        label: 'WP: Nibe – Ohne Hinweis',
        required: false,
        group: 'inv_wp',
        hinweis: null,
      },
    ],
  } as unknown as AnalyzeResult
}

function zeige(mappings: Record<string, string>) {
  return render(
    <MappingTabelle
      analysis={analyse()}
      mappings={mappings}
      invertierungen={{}}
      onSetMapping={vi.fn()}
      onToggleInvert={vi.fn()}
    />,
  )
}

describe('MappingTabelle — Erklärtext des Zielfelds', () => {
  it('zeigt den Hinweis, sobald ein Zielfeld gewählt ist', () => {
    zeige({ 'Produzierte Waerme WW': 'inv:42:warmwasser_kwh' })
    expect(screen.getByText(HINWEIS_THERMISCH)).toBeTruthy()
  })

  it('zeigt gar nichts, solange nichts zugeordnet ist', () => {
    // Ohne diese Hälfte wäre die Probe darüber auch bei einem Hinweis grün,
    // der unabhängig von der Auswahl immer dasteht.
    zeige({})
    expect(screen.queryByText(HINWEIS_THERMISCH)).toBeNull()
    expect(screen.queryByText(HINWEIS_ELEKTRISCH)).toBeNull()
  })

  it('unterscheidet die beiden Spalten — je Zeile der Text ihres eigenen Feldes', () => {
    // Der eigentliche Gegenstand: die thermische und die elektrische Spalte
    // liegen im Melder-Fall direkt nebeneinander und tragen dieselbe Einheit.
    // Ein Hinweis, der an beiden Zeilen derselbe wäre, hülfe nicht.
    zeige({
      'Produzierte Waerme WW': 'inv:42:warmwasser_kwh',
      'Verbrauchte Energie WW': 'inv:42:strom_warmwasser_kwh',
    })
    expect(screen.getByText(HINWEIS_THERMISCH)).toBeTruthy()
    expect(screen.getByText(HINWEIS_ELEKTRISCH)).toBeTruthy()
  })

  it('reserviert keine leere Zeile, wo das Feld keinen Hinweis führt', () => {
    const { container } = zeige({ 'Produzierte Waerme WW': 'inv:42:km_gefahren' })
    const leer = Array.from(container.querySelectorAll('p')).filter(
      (p) => p.textContent?.trim() === '',
    )
    expect(leer.length).toBe(0)
  })
})
