/**
 * Vergleichs-Badges rechnen mit den ANGEZEIGTEN Zahlen (N-253).
 *
 * Der Befund: `Delta` und `VglChip` bildeten den Prozentwert aus den Rohwerten
 * und standen damit neben zwei gerundeten Zahlen, denen sie widersprachen.
 * Gemessen am 29.08.2026 an den echten Formatierern:
 *
 *   Netzbezug 151,4 / 150,6 kWh  →  „151 · 151 · ▲ 1 %"      (gleiche Zahlen, Änderung behauptet)
 *   Einspeisung 1204 / 1200 kWh  →  „1.204 · 1.200 · ▲ 0 %"  (verschiedene Zahlen, Nulländerung behauptet)
 *
 * Dieselbe Klasse, die Striker in der Δ-Spalte der Werte-Tabelle gemeldet hat
 * (T89667 #162) — dort seit `e9f53a28` über `alsAngezeigt` gelöst. Beide Badges
 * sind geteilte SoT-Komponenten und tragen Cockpit **Tag, Monat und Jahr**.
 *
 * ⚑ Die letzten beiden Proben sind die GEGENPROBE: sie beschreiben, was der
 *   zurückgebaute Fix wieder täte. Ein Prüfer, der bei zurückgebautem Fix grün
 *   bleibt, hat nichts gemessen.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Delta, VglChip } from './MonatBilanz'

describe('Delta — der Prozentwert beschreibt die Zahlen, zwischen denen er steht', () => {
  it('zwei gleich aussehende kWh-Zahlen bekommen kein „▲ 1 %"', () => {
    // Beide Nachbarzellen zeigen „151" (fmt(…, 0)).
    render(<Delta a={151.4} b={150.6} dec={0} />)
    expect(screen.getByText(/=/).textContent).toBe('= 0 %')
  })

  it('sichtbar verschiedene Zahlen bekommen kein „= 0 %", sondern ihre Richtung', () => {
    render(<Delta a={1204} b={1200} dec={0} />)
    expect(screen.getByText(/▲/).textContent).toBe('▲ 0 %')
  })

  it('feinere Anzeige, feinere Aussage: dieselbe Paarung mit einer Nachkommastelle', () => {
    // Autarkie steht mit `dec = 1` da — dort SIND 8,0 und 8,0 gleich …
    const { unmount } = render(<Delta a={8.02} b={7.98} dec={1} />)
    expect(screen.getByText(/=/).textContent).toBe('= 0 %')
    unmount()
    // … bei zwei Stellen dagegen nicht mehr.
    render(<Delta a={8.02} b={7.98} dec={2} />)
    expect(screen.getByText(/▲/).textContent).toBe('▲ 1 %')
  })

  it('kein Badge, wo die Bezugsgröße als 0 dasteht', () => {
    const { container } = render(<Delta a={0.6} b={0.4} dec={0} />)
    expect(container.textContent).toBe('')
  })

  it('trägt bei sichtbarer Gleichheit den neutralen Ton, nicht „besser"', () => {
    render(<Delta a={151.4} b={150.6} dec={0} />)
    const el = screen.getByText(/=/)
    expect(el.className).toContain('bg-gray-50')
    expect(el.className).not.toContain('bg-green-50')
  })

  it('GEGENPROBE — aus den Rohwerten gerechnet stünde hier „▲ 1 %"', () => {
    // Das ist der zurückgebaute Rechenweg, wörtlich: ((a - b) / |b|) * 100.
    const roh = ((151.4 - 150.6) / Math.abs(150.6)) * 100
    expect(Math.round(roh)).toBe(1)
    // Genau diese 1 darf im Badge NICHT mehr auftauchen.
    render(<Delta a={151.4} b={150.6} dec={0} />)
    expect(screen.getByText(/=/).textContent).not.toContain('1 %')
  })
})

describe('VglChip — dieselbe Regel für die gestapelte Mobil-Ansicht', () => {
  it('gleich aussehende Zahlen: „=" statt einer erfundenen Richtung', () => {
    render(<VglChip prefix="VM" lang="Vormonat" ist={151.4} val={150.6} unit="kWh" dec={0} />)
    expect(screen.getByText(/VM/).textContent).toBe('VM = 0 %')
  })

  it('ohne tragfähige Bezugsgröße bleibt das „—" stehen', () => {
    render(<VglChip prefix="VJ" lang="Vorjahr" ist={12} val={null} unit="kWh" dec={0} />)
    expect(screen.getByText(/VJ/).textContent).toBe('VJ —')
  })

  it('GEGENPROBE — der Rohwert-Weg ergäbe „VM ▲ 1 %"', () => {
    render(<VglChip prefix="VM" lang="Vormonat" ist={151.4} val={150.6} unit="kWh" dec={0} />)
    expect(screen.getByText(/VM/).textContent).not.toBe('VM ▲ 1 %')
  })
})
