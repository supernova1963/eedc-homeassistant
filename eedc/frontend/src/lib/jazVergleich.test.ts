/**
 * N-350 — der Community-JAZ-Vergleich hat EINEN Ort, und die Beschriftung folgt der
 * tatsächlich verwendeten Bezugsgruppe.
 *
 * Der Fund: *Community → Übersicht* verglich art-spezifisch (`jaz_typ`),
 * *Community → Komponenten* gegen den Schnitt über alle Arten (`jaz`) — dieselbe
 * Anlage, zwei Prozent-Abweichungen, keine Seite nannte ihre Bezugsgruppe.
 *
 * ⚠ **Was diese Datei prüft und was der Wächter darunter prüft.** Hier steht die
 * Entscheidungsregel selbst. Dass die drei Anzeigestellen sie auch *rufen* — statt sie
 * erneut inline zu bilden —, hält `src/test/check-jaz-vergleich-sot.test.ts`; ein
 * Test auf die Regel allein bliebe grün, während eine Seite wieder `wp.jaz` liest
 * (genau der Zustand vor dem 29.08.2026).
 */
import { describe, it, expect } from 'vitest'
import { jazVergleichAnzeige } from './jazVergleich'
import type { WaermepumpeBenchmark } from '../api/community'

const jazNurGesamt: WaermepumpeBenchmark = {
  jaz: { wert: 3.4, community_avg: 3.8 },
  wp_art: 'luft_wasser',
}

const jazMitTyp: WaermepumpeBenchmark = {
  jaz: { wert: 3.4, community_avg: 3.8 },
  jaz_typ: { wert: 3.4, community_avg: 3.1 },
  wp_art: 'luft_wasser',
}

describe('jazVergleichAnzeige — welcher Vergleich wird gezeigt', () => {
  it('bevorzugt den art-spezifischen Vergleich, wenn der Server ihn liefert', () => {
    const a = jazVergleichAnzeige(jazMitTyp)
    // ⛔ Der Kern des Fundes: NICHT 3.8 (Schnitt über alle Arten), sondern 3.1.
    expect(a.kpi?.community_avg).toBe(3.1)
    expect(a.artSpezifisch).toBe(true)
  })

  it('fällt auf den Gesamtschnitt zurück, wenn `jaz_typ` fehlt', () => {
    const a = jazVergleichAnzeige(jazNurGesamt)
    expect(a.kpi?.community_avg).toBe(3.8)
    expect(a.artSpezifisch).toBe(false)
  })

  it('behandelt `jaz_typ` ohne community_avg wie „nicht vorhanden"', () => {
    // Der Server liefert das Feld, aber ohne Vergleichswert (zu wenige Anlagen der Art).
    // Es zu nehmen hieße, eine Kachel ohne Vergleich zu zeigen, obwohl einer da ist.
    const a = jazVergleichAnzeige({ ...jazNurGesamt, jaz_typ: { wert: 3.4, community_avg: null } })
    expect(a.kpi?.community_avg).toBe(3.8)
    expect(a.artSpezifisch).toBe(false)
  })
})

describe('jazVergleichAnzeige — die Beschriftung folgt der Bezugsgruppe', () => {
  it('nennt die Art NUR beim art-spezifischen Vergleich', () => {
    expect(jazVergleichAnzeige(jazMitTyp).artLabel).toBe('Luft/Wasser')
  })

  it('nennt KEINE Art, wenn gegen alle Arten verglichen wird', () => {
    // ⛔ Der zweite Teil des Fundes: vorher hing das Suffix an `wp_art` statt an der
    // benutzten Bezugsgruppe — „JAZ · Luft/Wasser" stand über einem Gesamtschnitt.
    expect(jazVergleichAnzeige(jazNurGesamt).artLabel).toBeNull()
  })

  it('zieht das Label aus dem SoT und kennt damit auch `brauchwasser`', () => {
    // Die früheren Inline-Ketten führten vier Arten; `WP_ART_LABELS` führt fünf.
    // Der Server nimmt `brauchwasser` als gültigen `wp_art` entgegen.
    const a = jazVergleichAnzeige({
      jaz: { wert: 2.9, community_avg: 3.0 },
      jaz_typ: { wert: 2.9, community_avg: 2.7 },
      wp_art: 'brauchwasser',
    })
    expect(a.artLabel).toBe('Brauchwasser')
  })

  it('gibt eine unbekannte Art unverändert durch, statt sie zu verschlucken', () => {
    const a = jazVergleichAnzeige({
      jaz_typ: { wert: 3.0, community_avg: 2.8 },
      wp_art: 'irgendwas_neues',
    })
    expect(a.artLabel).toBe('irgendwas_neues')
  })

  it('nimmt die Art der Anlage, wenn der Benchmark-Block keine trägt', () => {
    const a = jazVergleichAnzeige({ jaz_typ: { wert: 3.0, community_avg: 2.8 } }, 'sole_wasser')
    expect(a.artLabel).toBe('Sole/Wasser')
  })
})

describe('jazVergleichAnzeige — leere Lagen', () => {
  it('liefert nichts ohne Wärmepumpen-Block', () => {
    expect(jazVergleichAnzeige(undefined)).toEqual({ kpi: null, artSpezifisch: false, artLabel: null })
  })

  it('liefert nichts, wenn beide Vergleiche fehlen', () => {
    expect(jazVergleichAnzeige({ wp_art: 'luft_wasser' }).kpi).toBeNull()
  })

  it('zeigt die reine Zahl, wenn ein Vergleichswert fehlt — statt die Kachel zu schlucken', () => {
    // `community_avg: null` heißt „kein Vergleich", nicht „kein Wert": die Kachel
    // zeigt dann die eigene JAZ ohne Delta.
    const a = jazVergleichAnzeige({ jaz: { wert: 3.4 }, wp_art: 'luft_wasser' })
    expect(a.kpi?.wert).toBe(3.4)
    expect(a.artSpezifisch).toBe(false)
    expect(a.artLabel).toBeNull()
  })
})
