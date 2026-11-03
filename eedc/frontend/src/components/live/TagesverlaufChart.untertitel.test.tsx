import { beforeAll, describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { renderMitProvidern, stubMatchMedia } from '../../test/render'
import TagesverlaufChart from './TagesverlaufChart'

// Triage 3.11.2026 (B9): der Untertitel nennt keine Quelle — die Serien kommen aus HA oder MQTT, und die Antwort trägt
// keine Quelle je Serie. Ebenso der Hinweis zu nicht dargestellten Geräten.

describe('Live-Tagesverlauf — Texte quellenneutral', () => {
  beforeAll(() => stubMatchMedia())

  it('Untertitel ohne «HA-History», Hinweis ohne «HA-Leistungssensor»', () => {
    const serien = [{ key: 'netzbezug', label: 'Netz', kategorie: 'netz', farbe: 'currentColor', seite: 'quelle', bidirektional: false }]
    const punkte = [{ zeit: '10:00', werte: { netzbezug: 1.2 } }]
    renderMitProvidern(<TagesverlaufChart serien={serien} punkte={punkte} uebersprungen={['WP Garage']} />)
    expect(screen.getByText('10-Min-Durchschnitte aus den Live-Daten')).toBeInTheDocument()
    expect(screen.getByText(/Nicht dargestellt \(kein Leistungssensor zugeordnet\): WP Garage/)).toBeInTheDocument()
    expect(screen.queryByText(/HA-History|HA-Leistungssensor/)).not.toBeInTheDocument()
  })
})
