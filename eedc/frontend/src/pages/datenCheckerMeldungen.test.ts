/**
 * Rückmeldung der Bereichs-Reparatur — der Wächter gegen den falschen Erfolg.
 *
 * E2E an der lokalen Box (2026-07-30): `POST /reaggregate-bereich` antwortet mit
 * HTTP 200 und `{"status":"ok","erfolgreich":0,"keine_daten":11}`, wenn
 * `aggregate_day` für keinen Tag Kurvendaten findet. Die Seite meldete daraufhin
 * „Zeitraum … neu aus HA-Statistics aggregiert." — ein Erfolg, den es nicht gab.
 */
import { describe, it, expect } from 'vitest'
import { baueBereichsMeldung } from './datenCheckerMeldungen'

const VON = '2026-07-19'
const BIS = '2026-07-29'

describe('baueBereichsMeldung', () => {
  it('meldet KEINEN Erfolg, wenn kein einziger Tag geschrieben wurde', () => {
    const m = baueBereichsMeldung(
      { status: 'ok', verarbeitet: 11, erfolgreich: 0, keine_daten: 11, fehlgeschlagen: 0 },
      VON, BIS,
    )
    expect(m.art).toBe('hinweis')
    expect(m.text).toContain('kein Tag konnte nachgerechnet werden')
    expect(m.text).toContain('11 ohne verwertbare Daten')
    // Die Ursache muss dabeistehen, sonst sucht der Anwender bei sich.
    expect(m.text).toContain('Leistungssensor')
    // Und auf keinen Fall die alte Erfolgsformel.
    expect(m.text).not.toContain('neu aus HA-Statistics aggregiert.')
  })

  it('nennt bei Teil-Erfolg beide Zahlen', () => {
    const m = baueBereichsMeldung(
      { erfolgreich: 7, keine_daten: 4, fehlgeschlagen: 0 }, VON, BIS,
    )
    expect(m.art).toBe('hinweis')
    expect(m.text).toContain('7 Tag(e)')
    expect(m.text).toContain('4 ohne verwertbare Daten')
  })

  it('meldet Erfolg nur, wenn alle Tage durchgingen', () => {
    const m = baueBereichsMeldung(
      { erfolgreich: 11, keine_daten: 0, fehlgeschlagen: 0 }, VON, BIS,
    )
    expect(m.art).toBe('ok')
    expect(m.text).toBe(`Zeitraum ${VON} bis ${BIS}: 11 Tag(e) neu aus HA-Statistics aggregiert.`)
  })

  it('führt fehlgeschlagene Tage getrennt auf', () => {
    const m = baueBereichsMeldung(
      { erfolgreich: 0, keine_daten: 9, fehlgeschlagen: 2 }, VON, BIS,
    )
    expect(m.art).toBe('hinweis')
    expect(m.text).toContain('2 mit Fehler')
  })

  it('fällt bei fehlenden Zählern nicht auf einen Phantom-Erfolg zurück', () => {
    // Ältere Backends ohne Zähler-Felder: 0/0/0 → nichts zu beklagen, aber die
    // Meldung darf keine erfundene Tageszahl behaupten.
    const m = baueBereichsMeldung({ status: 'ok' }, VON, BIS)
    expect(m.art).toBe('ok')
    expect(m.text).toContain('0 Tag(e)')
  })
})
