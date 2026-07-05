/**
 * CommunityShareBlock — Kern der Rainer-Transparenz (2026-07-04):
 * 1. Die aufklappbare Feldliste zeigt GENAU die Felder des echten Submit-Payloads
 *    (vorhandene erscheinen, nicht gesendete nicht; Beispielwert = jüngster Monat).
 * 2. Einschalten des Teilen-Schalters löst die Erst-Übertragung aus (Variante A).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { GeteilteFelderDetail, CommunityTeilenSchalter } from './CommunityShareBlock'
import type { CommunityDataPreview } from '../api/community'

const refreshMock = vi.fn()
const updateMock = vi.fn().mockResolvedValue({})
const shareMock = vi.fn().mockResolvedValue({ success: true })

vi.mock('../hooks', () => ({
  useSelectedAnlage: () => ({
    selectedAnlage: { id: 1, anlagenname: 'Demo', community_auto_share: false, community_hash: null },
    selectedAnlageId: 1,
    refresh: refreshMock,
  }),
}))
vi.mock('../api', () => ({ anlagenApi: { update: (...a: unknown[]) => updateMock(...a) } }))
vi.mock('../api/community', () => ({
  communityApi: {
    share: (...a: unknown[]) => shareMock(...a),
    getPreview: vi.fn().mockResolvedValue(null),
  },
}))

const PAYLOAD: CommunityDataPreview = {
  region: 'BY',
  kwp: 20,
  ausrichtung: 'ost-west',
  neigung_grad: 26,
  speicher_kwh: 15.4,
  installation_jahr: 2022,
  hat_waermepumpe: true,
  hat_eauto: true,
  hat_wallbox: false,
  hat_balkonkraftwerk: false,
  hat_sonstiges: false,
  wp_art: 'luft_wasser',
  wallbox_kw: null,
  bkw_wp: null,
  sonstiges_bezeichnung: null,
  monatswerte: [
    {
      jahr: 2026, monat: 5, ertrag_kwh: 2100, einspeisung_kwh: 1500, netzbezug_kwh: 120,
      autarkie_prozent: 81.5, eigenverbrauch_prozent: 28.6,
      speicher_ladung_kwh: 300, speicher_entladung_kwh: 280,
      wp_stromverbrauch_kwh: 90, eauto_km: 512,
    },
    {
      // Juni: kein eauto_km → Beispielwert dafür muss aus Mai kommen
      jahr: 2026, monat: 6, ertrag_kwh: 2400, einspeisung_kwh: 1800, netzbezug_kwh: 90,
      autarkie_prozent: 84.2, eigenverbrauch_prozent: 25.1,
      speicher_ladung_kwh: 310, speicher_entladung_kwh: 290,
      wp_stromverbrauch_kwh: 60,
    },
  ],
}

describe('GeteilteFelderDetail', () => {
  it('listet genau die im Payload vorhandenen Felder mit jüngstem Beispielwert', () => {
    render(<GeteilteFelderDetail v={PAYLOAD} />)

    // Anlagendaten: Pflichtfelder + nur gesendete Komponenten-Angaben
    expect(screen.getByText('Installationsjahr')).toBeInTheDocument()
    expect(screen.getByText('Wärmepumpen-Art')).toBeInTheDocument()
    expect(screen.getByText('Luft/Wasser')).toBeInTheDocument()
    expect(screen.queryByText('Wallbox-Ladeleistung')).toBeNull()

    // Monats-Kennzahlen: vorhandene erscheinen (inkl. der „unbequemen")
    expect(screen.getByText('Netzbezug')).toBeInTheDocument()
    expect(screen.getByText('E-Auto gefahrene Kilometer')).toBeInTheDocument()
    // Referenz-Monat steht EINMAL in der Überschrift, nicht hinter jedem Wert
    // (R15-8: letzter abgeschlossener Monat — Fixture-Juni liegt in der Vergangenheit)
    expect(screen.getByText(/Beispielwerte aus Juni 2026 \(letzter abgeschlossener Monat\)/)).toBeInTheDocument()
    expect(screen.getByText('2.400,0 kWh')).toBeInTheDocument()
    // % mit Leerzeichen (Regel 0a)
    expect(screen.getByText('84,2 %')).toBeInTheDocument()
    // Nur ABWEICHENDE Werte tragen ihre Monatsangabe: eauto_km fehlt im Juni → Mai
    expect(screen.getByText('512,0 km (Mai 2026)')).toBeInTheDocument()

    // Nicht gesendete Felder erscheinen NICHT
    expect(screen.queryByText('Wallbox-Ladung')).toBeNull()
    expect(screen.queryByText('BKW-Erzeugung')).toBeNull()

    // Feld-Zähler in der Summary: 7 Anlagendaten + 9 Monats-Kennzahlen
    expect(screen.getByText(/16 Felder/)).toBeInTheDocument()
  })

  it('R15-8: der laufende Monat ist NICHT der Beispiel-Monat', () => {
    const heute = new Date()
    const lauf = { jahr: heute.getFullYear(), monat: heute.getMonth() + 1 }
    const vor = lauf.monat === 1
      ? { jahr: lauf.jahr - 1, monat: 12 }
      : { jahr: lauf.jahr, monat: lauf.monat - 1 }
    render(<GeteilteFelderDetail v={{
      ...PAYLOAD,
      monatswerte: [
        { jahr: vor.jahr, monat: vor.monat, ertrag_kwh: 100, einspeisung_kwh: 80, netzbezug_kwh: 10, autarkie_prozent: 90, eigenverbrauch_prozent: 20 },
        { jahr: lauf.jahr, monat: lauf.monat, ertrag_kwh: 50, einspeisung_kwh: 40, netzbezug_kwh: 5, autarkie_prozent: 91, eigenverbrauch_prozent: 21 },
      ],
    }} />)
    // Überschrift referenziert den Vormonat (abgeschlossen), nicht den laufenden
    expect(screen.getByText(new RegExp(`Beispielwerte aus \\S+ ${vor.jahr} \\(letzter abgeschlossener Monat\\)`))).toBeInTheDocument()
    // Beispielwert kommt aus dem abgeschlossenen Monat …
    expect(screen.getByText('100,0 kWh')).toBeInTheDocument()
    // … der laufende Wert erscheint nicht als Beispiel
    expect(screen.queryByText('50,0 kWh')).toBeNull()
  })
})

describe('CommunityTeilenSchalter', () => {
  beforeEach(() => { updateMock.mockClear(); shareMock.mockClear(); refreshMock.mockClear() })

  it('Einschalten speichert auto_share UND stößt die Erst-Übertragung an', async () => {
    render(<CommunityTeilenSchalter />)
    fireEvent.click(screen.getByRole('switch'))
    await waitFor(() => expect(refreshMock).toHaveBeenCalled())
    expect(updateMock).toHaveBeenCalledWith(1, { community_auto_share: true })
    expect(shareMock).toHaveBeenCalledWith(1)
  })

  it('bleibt eingeschaltet, auch wenn die Erst-Übertragung fehlschlägt', async () => {
    shareMock.mockRejectedValueOnce(new Error('Server offline'))
    render(<CommunityTeilenSchalter />)
    fireEvent.click(screen.getByRole('switch'))
    await waitFor(() => expect(refreshMock).toHaveBeenCalled())
    expect(updateMock).toHaveBeenCalledWith(1, { community_auto_share: true })
  })
})
