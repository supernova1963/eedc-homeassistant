/**
 * Der API-Client und die Einstellungs-Sperre.
 *
 * Zwei Zusagen werden hier festgehalten, weil beide leicht still kaputtgehen:
 * der Nachweis fährt bei jedem Aufruf mit, und ein 423 führt genau **einmal** zum
 * Entsperr-Dialog und zur Wiederholung — nicht zu einer Schleife.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from './client'
import {
  SPERRE_HEADER,
  entsperrDialogAnmelden,
  nachweisLoeschen,
  nachweisSetzen,
} from '../lib/sperreSpeicher'

function antwort(status: number, body: unknown = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('API-Client mit Einstellungs-Sperre', () => {
  beforeEach(() => {
    nachweisLoeschen()
    entsperrDialogAnmelden(null)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    nachweisLoeschen()
    entsperrDialogAnmelden(null)
  })

  it('schickt keinen Nachweis mit, solange nichts entsperrt ist', async () => {
    const f = vi.spyOn(globalThis, 'fetch').mockResolvedValue(antwort(200, { ok: true }))

    await api.get('/anlagen/')

    const kopf = (f.mock.calls[0][1] as RequestInit).headers as Record<string, string>
    expect(kopf[SPERRE_HEADER]).toBeUndefined()
  })

  it('schickt den Nachweis mit, sobald er vorliegt', async () => {
    nachweisSetzen('nachweis-123')
    const f = vi.spyOn(globalThis, 'fetch').mockResolvedValue(antwort(200, { ok: true }))

    await api.post('/anlagen/', { name: 'x' })

    const kopf = (f.mock.calls[0][1] as RequestInit).headers as Record<string, string>
    expect(kopf[SPERRE_HEADER]).toBe('nachweis-123')
  })

  it('öffnet bei 423 den Dialog und wiederholt den Aufruf danach', async () => {
    const f = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(antwort(423, { detail: 'gesperrt', sperre: true }))
      .mockResolvedValueOnce(antwort(200, { ok: true }))

    const dialog = vi.fn(async () => {
      nachweisSetzen('frisch')
      return true
    })
    entsperrDialogAnmelden(dialog)

    await expect(api.post('/anlagen/', { name: 'x' })).resolves.toEqual({ ok: true })

    expect(dialog).toHaveBeenCalledTimes(1)
    expect(f).toHaveBeenCalledTimes(2)
    const zweiterKopf = (f.mock.calls[1][1] as RequestInit).headers as Record<string, string>
    expect(zweiterKopf[SPERRE_HEADER]).toBe('frisch')
  })

  it('wiederholt nur EINMAL — ein dauerhaft gesperrter Aufruf dreht sich nicht im Kreis', async () => {
    const f = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      antwort(423, { detail: 'gesperrt', sperre: true }),
    )
    entsperrDialogAnmelden(async () => true)

    await expect(api.post('/anlagen/', {})).rejects.toThrow()

    expect(f).toHaveBeenCalledTimes(2)
  })

  it('bricht der Anwender ab, kommt der Fehler durch — ohne zweiten Versuch', async () => {
    const f = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      antwort(423, { detail: 'gesperrt', sperre: true }),
    )
    const dialog = vi.fn(async () => false)
    entsperrDialogAnmelden(dialog)

    await expect(api.post('/anlagen/', {})).rejects.toThrow()

    expect(dialog).toHaveBeenCalledTimes(1)
    expect(f).toHaveBeenCalledTimes(1)
  })

  it('lesende Aufrufe lösen keinen Dialog aus', async () => {
    // Gegenprobe zur Zusage „Ansehen ist nie gesperrt": Selbst wenn der Server einen
    // 423 auf ein GET schickte, dürfte der Client daraus keinen Dialog machen — sonst
    // stünde er dem Betrachter im Weg, der gar nichts ändern wollte.
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(antwort(200, { ok: true }))
    const dialog = vi.fn(async () => true)
    entsperrDialogAnmelden(dialog)

    await api.get('/anlagen/')

    expect(dialog).not.toHaveBeenCalled()
  })
})
