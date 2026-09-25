import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TKonto } from './TKonto'
import { aktuellerMonat } from '../../test/factories'

/**
 * N-555 (Nebenfund 2) — die eMob-Zeile des T-Kontos nennt die Werte, mit denen
 * gerechnet wurde. Bis 25.09.2026 stand im Tooltip der Aggregat-Zeile fest
 * „km × 7/100 × 1,80 €" — zwei Defaults, die die Rechnung seit dem Drift-Audit A2
 * nicht mehr nimmt (sie rechnet je Fahrzeug mit SEINEM Vergleichsverbrauch und dem
 * Benzinpreis des Monats). Der Rechenweg kommt jetzt aus dem Backend
 * (`emob_ersparnis_berechnung`). Tooltip am Label öffnen (s. a6-Test).
 */
describe('T-Konto — eMob-Ersparnis nennt die eingesetzten Werte', () => {
  it('zeigt den Rechenweg aus dem Backend, keine festen 7 L × 1,80 €', () => {
    const d = aktuellerMonat(2025, 3, {
      anlage_name: 'Demo',
      emob_ersparnis_euro: 120.5, emob_km: 1500, emob_ladung_netz_kwh: 150,
      emob_ersparnis_berechnung: '1500 km × 6,5 L/100km × 1,74 €',
    })
    render(<TKonto d={d} />)
    fireEvent.mouseEnter(screen.getAllByText(/eMob-Ersparnis vs\. Verbrenner/)[0])
    expect(screen.getAllByText(/6,5 L\/100km × 1,74 €/).length).toBeGreaterThan(0)
    expect(screen.queryByText(/7\/100/)).toBeNull()
    expect(screen.queryByText(/1,80 €/)).toBeNull()
  })
})
