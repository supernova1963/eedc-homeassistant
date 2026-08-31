/**
 * Der Befund sagt, WORAN eedc gesucht hat — nicht nur, was es fand.
 *
 * ⚠ **Warum das eine eigene Probe verdient.** Bis zum 31.08.2026 stand hier
 * dreimal der Satz „die Erkennung sucht an der Entity-ID". Er war richtig,
 * solange es nur den einen Weg gab. Seit dem Umbau auf `integration_entities()`
 * + `unique_id` ist er nur noch für den **Rückfall** wahr — und wer ihn im
 * Normalfall zu lesen bekommt, sucht bei sich nach einem Namensproblem, das er
 * gar nicht hat. Ein Hinweistext, der eine überholte Ursache nennt, ist
 * derselbe Fehler wie eine falsche Zahl, nur schwerer zu bemerken.
 *
 * Gemeldet hat den Anlass **Burkard** (#401): seine sechs SFML-Entities heißen
 * `sensor.none_*`, er musste in den Add-on-Container sehen, um zu erfahren,
 * dass vier Rollen fehlen.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import PrognoseQuellenBefund from './PrognoseQuellenBefund'
import type { PrognoseQuellenStatus } from '../../api/aussichten'

const rolle = (r: string, gefunden: boolean, wesentlich = false) => ({
  rolle: r, label: r, gefunden, entity_id: gefunden ? `sensor.${r}` : null,
  wert: gefunden ? 1 : null, wesentlich,
  stufe: gefunden ? ('unique_id' as const) : null,
})

const status = (over: Partial<PrognoseQuellenStatus>): Record<string, PrognoseQuellenStatus> => ({
  sfml: {
    integration: 'sfml',
    gefunden: true,
    fehler: null,
    rollen: [rolle('heute_kwh', true), rolle('stundenprofil', true)],
    anzahl_gefunden: 2,
    anzahl_gesamt: 2,
    fehlend_wesentlich: [],
    menge_quelle: 'integration_entities',
    rolle_quelle: 'unique_id',
    anzahl_entities: 53,
    ...over,
  } as PrognoseQuellenStatus,
})

describe('PrognoseQuellenBefund nennt den benutzten Weg', () => {
  it('sagt bei vollständiger Erkennung, dass die Namen egal waren', () => {
    render(<PrognoseQuellenBefund quelle="sfml" status={status({})} />)
    expect(screen.getByText(/alle 2 Sensoren erkannt/)).toBeInTheDocument()
    expect(screen.getByText(/unabhängig von ihren Namen/)).toBeInTheDocument()
  })

  it('rät NICHT zum Namensproblem, wenn die Integration die Menge geliefert hat', () => {
    // Der Fall: HA hat die Zugehörigkeit gesagt, eine Rolle fehlt trotzdem.
    // Dann liegt es an der Version der Integration, nicht an den Namen — und
    // genau das muss dastehen, sonst benennt jemand seine Entitäten um.
    render(<PrognoseQuellenBefund quelle="sfml" status={status({
      rollen: [rolle('heute_kwh', true), rolle('stundenprofil', false, true)],
      anzahl_gefunden: 1, fehlend_wesentlich: ['stundenprofil'],
    })} />)
    expect(screen.getByText(/53 Entitäten dieser Integration/)).toBeInTheDocument()
    expect(screen.queryByText(/sucht deshalb an der Entity-ID/)).not.toBeInTheDocument()
  })

  it('rät SEHR WOHL zum Namensproblem, wenn nur die Präfix-Liste trug', () => {
    render(<PrognoseQuellenBefund quelle="sfml" status={status({
      menge_quelle: 'praefix', rolle_quelle: 'muster',
      rollen: [rolle('heute_kwh', true), rolle('stundenprofil', false, true)],
      anzahl_gefunden: 1, fehlend_wesentlich: ['stundenprofil'],
    })} />)
    expect(screen.getByText(/sucht deshalb an der Entity-ID/)).toBeInTheDocument()
  })

  it('unterscheidet auch bei NULL Treffern die beiden Ursachen', () => {
    const { unmount } = render(<PrognoseQuellenBefund quelle="sfml" status={status({
      gefunden: false, anzahl_gefunden: 0, menge_quelle: 'integration_entities',
    })} />)
    expect(screen.getByText(/meldet dafür aber keine Entitäten/)).toBeInTheDocument()
    unmount()

    render(<PrognoseQuellenBefund quelle="sfml" status={status({
      gefunden: false, anzahl_gefunden: 0, menge_quelle: 'praefix',
    })} />)
    expect(screen.getByText(/nicht mitgeteilt, welche Entitäten/)).toBeInTheDocument()
  })
})
