/**
 * F-28 — die PV-Prognose-Quelle hängt an der VERBINDUNG, nicht an der Betriebsart.
 *
 * Der Backend-Weg ist seit N-156 offen (`prognose_router.resolve_prognose_quelle`
 * liefert SFML auch über eine Token-Anbindung, Solcast findet seine Sensoren dort
 * ohne eigenen API-Schlüssel). Das Auswahlfeld sperrte SFML trotzdem weiter am
 * Supervisor-Flag `ha_integration_available` — der Backend-Fix war damit für genau
 * den Betrieb unerreichbar, für den er gebaut wurde.
 */
import { describe, it, expect } from 'vitest'
import { bauePrognoseQuelleOptionen, prognoseQuelleHinweis } from './AnlageForm'

const sfml = (haVerbunden: boolean) =>
  bauePrognoseQuelleOptionen(haVerbunden).find(o => o.value === 'sfml')!

describe('PV-Prognose-Quelle — Auswahl folgt der HA-Verbindung', () => {
  it('SFML ist mit verbundener HA-Instanz wählbar (Add-on ODER Token)', () => {
    expect(sfml(true).disabled).toBe(false)
    expect(sfml(true).label).not.toMatch(/Add-on/)
  })

  it('SFML bleibt ohne HA-Verbindung gesperrt und sagt warum', () => {
    expect(sfml(false).disabled).toBe(true)
    expect(sfml(false).label).toMatch(/verbundenem Home Assistant/)
  })

  it('kein Text behauptet mehr, es gehe „nur im HA-Add-on"', () => {
    const texte = [
      ...bauePrognoseQuelleOptionen(true).map(o => o.label),
      ...bauePrognoseQuelleOptionen(false).map(o => o.label),
      ...['eedc', 'solcast', 'sfml'].flatMap(q => [
        prognoseQuelleHinweis(q, true),
        prognoseQuelleHinweis(q, false),
      ]),
    ]
    expect(texte.filter(t => /nur im HA-Add-on|nur HA-Add-on/.test(t))).toEqual([])
  })

  it('der Solcast-Hinweis nennt bei bestehender Verbindung keinen eigenen API-Schlüssel als Bedingung', () => {
    expect(prognoseQuelleHinweis('solcast', true)).toMatch(/ohne eigenen API-Schlüssel/)
    expect(prognoseQuelleHinweis('solcast', false)).toMatch(/API-Token muss konfiguriert sein/)
  })

  it('eedc bleibt unabhängig von Home Assistant', () => {
    const eedc = bauePrognoseQuelleOptionen(false).find(o => o.value === 'eedc')!
    expect(eedc.disabled).toBeUndefined()
    expect(prognoseQuelleHinweis('eedc', false)).toMatch(/auch standalone/)
  })
})
