import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { KPICard } from './KPICard'
import { LEER_TOKEN } from '../../lib/einheiten'

/**
 * **Steht „—" im Feld, steht im Tooltip keine gefüllte Rechnung** (Entscheid Gernot
 * 30.09.2026, N-579).
 *
 * ## Warum das eine Probe braucht
 *
 * Wert und Rechnung hingen an **verschiedenen** Bedingungen. In `v4/TagBilanz.tsx`
 * zeigte die Autarkie-Kachel „—" (`t.autarkie == null`) und darunter die gefüllte
 * Rechnung „(35 − 1) ÷ 35 kWh" (`t.gesamtverbrauch > 0`) — ohne Ergebnis. Der Leser
 * teilt selbst und kommt auf 97 %, eine Zahl, die eedc bewusst zurückhält; und der
 * Netzbezug darin ist die **gekürzte** Summe (eedc hat eine unplausible Menge
 * verworfen), der selbst gerechnete Wert wäre also zusätzlich falsch. Gemeldet von
 * mameier1234, T89667 #388.
 *
 * ## Warum die Regel in `KPICard` sitzt und nicht an den Kacheln
 *
 * Gemessen am 30.09.: rund 44 Kachel-Definitionen in vierzehn Dateien reichen
 * `berechnung` durch. Die Regel dort zu ziehen wären 44 Bedingungen, die die nächste
 * neue Kachel wieder bricht. `KPICard` ist die eine Stelle, die den **Wert** und den
 * Tooltip zugleich kennt.
 *
 * ⚠ **`formel` bleibt sichtbar** — sie nennt die Größe („(Gesamtverbrauch − Netzbezug)
 * ÷ Gesamtverbrauch × 100") und ergibt keinen Wert. Weggenommen wird nur, was mit
 * echten Zahlen gefüllt ist.
 *
 * ⚑ Der `FormelTooltip` baut seinen Inhalt erst bei `mouseEnter`, und zwar auf dem
 * **Wert** — dieselbe Geste wie in `KomponentenSektionen.jaz-herleitung.test.tsx`.
 */

const FORMEL = '(Gesamtverbrauch − Netzbezug) ÷ Gesamtverbrauch × 100'
const BERECHNUNG = '(35,0 − 1,0) ÷ 35,0 kWh'
const ERGEBNIS = '= 97,1 %'

function oeffne(wert: string) {
  fireEvent.mouseEnter(screen.getAllByText(wert)[0])
}

describe.each([['sm' as const], ['md' as const]])('KPICard (size=%s)', (size) => {
  it('zeigt bei „—" die Formel, aber KEINE gefüllte Rechnung und kein Ergebnis', () => {
    render(
      <KPICard
        title="Autarkie" value={LEER_TOKEN} unit="%" size={size}
        formel={FORMEL} berechnung={BERECHNUNG} ergebnis={ERGEBNIS}
      />,
    )
    oeffne(LEER_TOKEN)
    expect(screen.getByText(FORMEL)).toBeInTheDocument()
    expect(screen.queryByText(BERECHNUNG)).not.toBeInTheDocument()
    expect(screen.queryByText(ERGEBNIS)).not.toBeInTheDocument()
    // Die Überschrift „Berechnung" darf ebenfalls nicht stehen — sonst bliebe ein
    // leerer Abschnitt zurück, der aussieht, als fehlte etwas.
    expect(screen.queryByText('Berechnung')).not.toBeInTheDocument()
  })

  it('Gegenprobe: mit Wert stehen Rechnung und Ergebnis wie bisher', () => {
    render(
      <KPICard
        title="Autarkie" value="97,1" unit="%" size={size}
        formel={FORMEL} berechnung={BERECHNUNG} ergebnis={ERGEBNIS}
      />,
    )
    oeffne('97,1')
    expect(screen.getByText(FORMEL)).toBeInTheDocument()
    expect(screen.getByText(BERECHNUNG)).toBeInTheDocument()
    expect(screen.getByText(ERGEBNIS)).toBeInTheDocument()
  })
})
