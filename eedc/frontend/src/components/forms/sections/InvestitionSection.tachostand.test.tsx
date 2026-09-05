/**
 * #407 (8ear) — der Tachostand rechnet die gefahrenen Kilometer, während man tippt.
 *
 * Das Backend liefert den Anfang (`FeldStatus.stand_vormonat`), der Client zeigt
 * `Stand − Anfang` unter dem Feld und bietet die Übernahme in „Gefahrene km" an.
 * Drei Lagen, drei Aussagen: Anfang bekannt → Rechnung mit Übernahme · kein Anfang
 * (erster Monat) → Hinweis statt erfundener Zahl · Stand rückwärts → Warnung.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Car } from 'lucide-react'

import { InvestitionSection } from './InvestitionSection'
import type { Investition } from '../../../types'
import type { FeldStatus } from '../../../api/monatsabschluss'
import type { FeldDefinition } from '../../../lib/fieldDefinitions'

const inv = { id: 7, typ: 'e-auto', bezeichnung: 'ID.3', parameter: {} } as unknown as Investition

const FELDER: FeldDefinition[] = [
  { feld: 'km_gefahren', label: 'Gefahrene km', einheit: 'km' },
  { feld: 'km_stand', label: 'Tachostand', einheit: 'km', differenzZiel: 'km_gefahren' },
]

function status(standVormonat: number | null): (invId: number, feld: string) => FeldStatus | undefined {
  return (_id, feld) =>
    feld === 'km_stand'
      ? ({ feld, label: 'Tachostand', einheit: 'km', aktueller_wert: null, aktueller_text: null,
          quelle: null, vorschlaege: [], warnungen: [], strategie: null, sensor_id: null,
          typ: 'number', gruppe: null, stand_vormonat: standVormonat } as FeldStatus)
      : undefined
}

function zeichne(daten: Record<string, string>, standVormonat: number | null) {
  const onInvChange = vi.fn()
  render(
    <InvestitionSection
      title="E-Auto" icon={Car} iconColor="text-cyan-500"
      investitionen={[inv]}
      investitionsDaten={{ 7: daten }}
      onInvChange={onInvChange}
      felder={FELDER}
      sonstigePositionen={{}}
      onPositionenChange={() => {}}
      feldStatus={status(standVormonat)}
    />,
  )
  return onInvChange
}

describe('#407 — Tachostand → gefahrene km', () => {
  it('zeigt Ende − Anfang und übernimmt die Differenz auf Klick', () => {
    const onInvChange = zeichne({ km_stand: '45230' }, 44100)
    expect(screen.getByText(/45\.230 − 44\.100/)).toBeInTheDocument()
    expect(screen.getByText(/1\.130 km/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /als Gefahrene km übernehmen/ }))
    expect(onInvChange).toHaveBeenCalledWith(7, 'km_gefahren', '1130')
  })

  it('markiert die Übernahme, sobald die Menge der Differenz entspricht', () => {
    zeichne({ km_stand: '45230', km_gefahren: '1130' }, 44100)
    expect(screen.getByText(/übernommen/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /übernehmen/ })).toBeNull()
  })

  it('erfindet ohne Anfang keine Zahl — erster Monat', () => {
    const onInvChange = zeichne({ km_stand: '45230' }, null)
    expect(screen.getByText(/Erster Tachostand/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /übernehmen/ })).toBeNull()
    expect(onInvChange).not.toHaveBeenCalled()
  })

  it('warnt, wenn der Stand unter dem Vormonat liegt, und bietet nichts an', () => {
    zeichne({ km_stand: '44100' }, 45230)
    expect(screen.getByText(/läuft nicht rückwärts/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /übernehmen/ })).toBeNull()
  })

  it('zeigt ohne getippten Stand nichts', () => {
    zeichne({}, 44100)
    expect(screen.queryByText(/Tachostand:/)).toBeNull()
    expect(screen.queryByText(/Erster Tachostand/)).toBeNull()
  })
})
