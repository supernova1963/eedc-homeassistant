/**
 * Rückmeldung der Bereichs-Reparatur — der Wächter gegen den falschen Erfolg.
 *
 * E2E an der lokalen Box (2026-07-30): `POST /reaggregate-bereich` antwortet mit
 * HTTP 200 und `{"status":"ok","erfolgreich":0,"keine_daten":11}`, wenn
 * `aggregate_day` für keinen Tag Kurvendaten findet. Die Seite meldete daraufhin
 * „Zeitraum … neu aus HA-Statistics aggregiert." — ein Erfolg, den es nicht gab.
 */
import { describe, it, expect } from 'vitest'
import { baueBereichsMeldung, baueTagesMeldung } from './datenCheckerMeldungen'

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

/**
 * N-58: derselbe Kanon je Komponente. Bis v4.0.6 baute der Einzeltag-Pfad seine
 * Meldung allein aus `pv_kwh_alt`/`pv_kwh_neu` und meldete immer Erfolg — eine
 * Wärmepumpe ohne geschriebenen Wert war von „PV unverändert" nicht zu
 * unterscheiden (Forum simon42 #89667/83, dietmar1968).
 */
describe('baueTagesMeldung', () => {
  const DATUM = '2026-07-28'

  it('meldet Erfolg nur, wenn alle Komponenten einen Wert tragen', () => {
    const m = baueTagesMeldung(
      {
        status: 'ok', pv_kwh_alt: 0, pv_kwh_neu: 30,
        komponenten_erwartet: 3, komponenten_geschrieben: 3, komponenten_ohne_wert: [],
      },
      DATUM,
    )
    expect(m.art).toBe('ok')
    // Die PV-Aussage (#290) bleibt erhalten …
    expect(m.text).toContain('PV 0,0 → 30,0 kWh')
    // … und die Komponenten-Aussage kommt dazu.
    expect(m.text).toContain('Alle 3 zugeordneten Komponenten tragen einen Wert.')
  })

  it('nennt bei Teil-Erfolg die Komponente, für die nichts geschrieben wurde', () => {
    const m = baueTagesMeldung(
      {
        status: 'ok', pv_kwh_alt: 0, pv_kwh_neu: 30,
        komponenten_erwartet: 3, komponenten_geschrieben: 2,
        komponenten_ohne_wert: ['Wärmepumpe'],
      },
      DATUM,
    )
    expect(m.art).toBe('hinweis')
    expect(m.text).toContain('2 von 3 Komponenten')
    expect(m.text).toContain('Wärmepumpe')
    // Absage ohne Weg ist eine halbe Meldung.
    expect(m.text).toContain('Leistungssensor')
  })

  it('meldet KEINEN Erfolg, wenn für keine Komponente etwas geschrieben wurde', () => {
    const m = baueTagesMeldung(
      {
        status: 'ok', pv_kwh_alt: 12, pv_kwh_neu: 12,
        komponenten_erwartet: 2, komponenten_geschrieben: 0,
        komponenten_ohne_wert: ['Einspeisung', 'Wärmepumpe'],
      },
      DATUM,
    )
    expect(m.art).toBe('hinweis')
    expect(m.text).toContain('Für keine der 2 zugeordneten Komponenten')
    expect(m.text).toContain('Einspeisung, Wärmepumpe')
    expect(m.text).toContain('Leistungssensor')
  })

  it('bleibt bei älteren Backends ohne Komponenten-Zähler bei der PV-Aussage', () => {
    const m = baueTagesMeldung(
      { status: 'ok', pv_kwh_alt: 30, pv_kwh_neu: 30 }, DATUM,
    )
    expect(m.art).toBe('ok')
    expect(m.text).toBe(`Tag ${DATUM}: PV-Wert blieb 30,0 kWh (keine Änderung).`)
  })

  it('kommt ohne PV-Zahlen aus (Tag ohne bestehende Zusammenfassung)', () => {
    const m = baueTagesMeldung(
      {
        status: 'ok', pv_kwh_alt: null, pv_kwh_neu: null,
        komponenten_erwartet: 1, komponenten_geschrieben: 0,
        komponenten_ohne_wert: ['Wärmepumpe'],
      },
      DATUM,
    )
    expect(m.art).toBe('hinweis')
    expect(m.text).toContain(`Tag ${DATUM} aus HA-Statistics neu aggregiert.`)
    expect(m.text).toContain('Wärmepumpe')
  })
})
