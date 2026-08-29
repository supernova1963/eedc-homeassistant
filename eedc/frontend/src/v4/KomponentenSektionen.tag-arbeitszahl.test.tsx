import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import type { ParkApi } from '../components/park'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import { aktuellerMonat, tagWerte } from '../test/factories'
import { baueTagAlsMonat } from './TagKomponenten'
import type { TagDetail } from '../api/energie_profil'

/**
 * **N-348** — die drei Arbeitszahlen je Funktion verschwinden im Tag nicht mehr
 * lautlos (SOLL Wärme/Klima §3.3/**S3**).
 *
 * ## Der Befund, den diese Datei festhält
 *
 * Die Blockfabrik ist für Monat **und** Tag dieselbe, und `jazZeile` rendert
 * eine Zeile erst, wenn **Wert oder Grund** gesetzt ist. Der Monat lieferte
 * immer beides, der Tagespfad keines von beidem — die drei Zeilen fielen unter
 * *Cockpit → Tag* **ersatzlos** weg. Nicht als „—", sondern gar nicht, und
 * damit von „nicht getrennt gemessen" nicht zu unterscheiden. Genau das
 * verbietet S3: *„Eine Sicht, die weniger zeigt als die Nachbarsicht, sagt
 * warum."* Der Kommentar über `jazZeile` sagt es selbst.
 *
 * ## Warum die Probe hier steht und nicht nur im Backend
 *
 * Der Backend-Wächter (`test_n348_tag_arbeitszahl_je_funktion.py`) hält fest,
 * dass die **Antwort** je Funktion Wert oder Grund trägt. Er bliebe grün, wenn
 * die Fabrik die Felder nicht mehr **rendert** — das ist die N-274-Bauform, und
 * sie ist an dieser Fläche schon einmal zugeschlagen (`check:mobilkarte` maß den
 * Bauort und hätte den Verlust der Zahlen nicht gesehen). Deshalb hier die
 * Sicht: dieselbe Fabrik, Periode `tag`, und die Zeilen müssen dastehen.
 *
 * ⛔ **Die erste Fassung dieser Datei prüfte NUR die Fabrik — und war damit blind
 * für den Defekt.** Gegenprobe am 29.08.: Wird die Durchreichung in
 * `baueTagAlsMonat` entfernt (also genau der Bau, den diese Datei sichern soll),
 * bleiben alle Rendering-Proben **grün**. Sie bekommen ihre Daten ja direkt.
 * Deshalb steht unten der zweite Block: er hält die **Naht** zwischen
 * Tages-Antwort und Fabrik. *Ein Prüfer, der neben der Fundstelle misst, misst
 * nichts.*
 *
 * Schwesterdatei: `KomponentenSektionen.soll-waerme-klima.test.tsx` (Achse III/IV).
 */

const NOOP: ParkApi = {
  aktiv: false, istGeparkt: () => false, park: () => {}, entparke: () => {},
  zuruecksetzen: () => {}, geparkt: [], registriere: () => () => {}, parkbareAnzahl: 0,
}

/** Der WP-Block in einer gewählten Periode. */
function rendereWpBlock(over: Partial<AktuellerMonatResponse>, periode: 'monat' | 'tag') {
  const block = baueKomponentenBloecke(aktuellerMonat(2026, 8, over), NOOP, periode)
    .find((b) => b.id === 'k-waermepumpe')
  expect(block, 'Wärme/Klima-Block muss entstehen').toBeDefined()
  render(<>{block!.render(false)}</>)
}

/** Die Antwort, wie der Tages-Endpunkt sie seit N-348 liefert. */
const TAG_MIT_ZAHLEN: Partial<AktuellerMonatResponse> = {
  wp_strom_kwh: 30, wp_waerme_kwh: 100,
  wp_strom_heizen_kwh: 20, wp_strom_warmwasser_kwh: 10,
  wp_jaz: 3.33,
  wp_jaz_heizen: 4.0, wp_jaz_warmwasser: 2.0,
  wp_jaz_kuehlen: null, wp_jaz_kuehlen_grund: 'kein Kühlbetrieb in diesem Zeitraum',
}

describe('N-348 — Cockpit → Tag zeigt die Arbeitszahl je Funktion', () => {
  it('rendert alle drei Zeilen in der Tagessicht', () => {
    rendereWpBlock(TAG_MIT_ZAHLEN, 'tag')

    expect(screen.getByText('Arbeitszahl · Heizen')).toBeInTheDocument()
    expect(screen.getByText('Arbeitszahl · Warmwasser')).toBeInTheDocument()
    expect(screen.getByText('Arbeitszahl · Kühlen')).toBeInTheDocument()
  })

  it('zeigt die Werte, nicht nur die Beschriftung', () => {
    // ⚑ Die Zeile allein genügt nicht — ein Rückbau, der die Labels stehen
    // lässt und die Zahlen verliert, wäre sonst grün (N-274-Bauform).
    rendereWpBlock(TAG_MIT_ZAHLEN, 'tag')

    expect(screen.getByText('4,00')).toBeInTheDocument()
    expect(screen.getByText('2,00')).toBeInTheDocument()
  })

  it('das gesperrte „—" trägt seinen Grund — nie ein nacktes „—"', () => {
    rendereWpBlock({
      ...TAG_MIT_ZAHLEN,
      wp_jaz_heizen: null,
      wp_jaz_heizen_grund: 'Strom nicht getrennt je Funktion gemessen',
      wp_jaz_warmwasser: null,
      wp_jaz_warmwasser_grund: 'Strom nicht getrennt je Funktion gemessen',
    }, 'tag')

    expect(screen.getByText('Arbeitszahl · Heizen')).toBeInTheDocument()
    expect(
      screen.getAllByText('— (Strom nicht getrennt je Funktion gemessen)').length,
    ).toBe(2)
  })

  it('DER KERN: ohne Wert UND ohne Grund verschwindet die Zeile — das war der Defekt', () => {
    // Diese Probe hält die **Ursache** fest, nicht ihre Behebung: Die Fabrik
    // verhält sich unverändert (und soll das auch — eine Zeile ohne jede
    // Auskunft hat keinen Inhalt). Der Fehler saß darin, dass der Tagespfad
    // genau diesen Zustand lieferte. Wer die Durchreichung in
    // `TagKomponenten.tsx` oder die Felder im Backend entfernt, landet wieder
    // hier — und sieht an dieser Probe, warum die Zeile dann fehlt.
    rendereWpBlock({
      wp_strom_kwh: 30, wp_waerme_kwh: 100,
      wp_strom_heizen_kwh: 20, wp_strom_warmwasser_kwh: 10,
      wp_jaz: 3.33,
      wp_jaz_heizen: null, wp_jaz_heizen_grund: null,
      wp_jaz_warmwasser: null, wp_jaz_warmwasser_grund: null,
      wp_jaz_kuehlen: null, wp_jaz_kuehlen_grund: null,
    }, 'tag')

    expect(screen.queryByText('Arbeitszahl · Heizen')).toBeNull()
    expect(screen.queryByText('Arbeitszahl · Warmwasser')).toBeNull()
    expect(screen.queryByText('Arbeitszahl · Kühlen')).toBeNull()
  })

  it('Monat und Tag antworten in derselben Datenlage gleich', () => {
    // ⭐ Die Aussage des Fundes in einer Probe: Es ging nie darum, dass eine
    // Zahl fehlte, sondern dass ZWEI SICHTEN DERSELBEN ANLAGE verschieden viel
    // sagten. Beide Perioden laufen durch dieselbe Fabrik; dass sie dasselbe
    // rendern, ist deshalb eine Aussage über die Eingangsdaten.
    for (const periode of ['monat', 'tag'] as const) {
      const { unmount } = render(<></>)
      unmount()
      rendereWpBlock(TAG_MIT_ZAHLEN, periode)
      expect(
        screen.getAllByText('Arbeitszahl · Warmwasser').length,
        `Periode ${periode}`,
      ).toBeGreaterThan(0)
    }
  })
})

// ══ Die Naht: Tages-Antwort → Fabrik ═══════════════════════════════════════

/** Ein Tag mit WP-Strom — sonst entsteht der Block gar nicht. */
function tagMit(detail: Partial<TagDetail>) {
  return baueTagAlsMonat(
    tagWerte('2026-08-29', { wp_strom: 30.0 }),
    [], [], detail as TagDetail,
  )
}

describe('N-348 — die Durchreichung in baueTagAlsMonat', () => {
  it('reicht Wert UND Grund je Funktion durch', () => {
    const d = tagMit({
      wp_jaz_heizen: 4.0, wp_jaz_heizen_grund: null,
      wp_jaz_warmwasser: null,
      wp_jaz_warmwasser_grund: 'Strom nicht getrennt je Funktion gemessen',
      wp_jaz_kuehlen: null,
      wp_jaz_kuehlen_grund: 'kein Kühlbetrieb in diesem Zeitraum',
    })

    expect(d.wp_jaz_heizen).toBe(4.0)
    expect(d.wp_jaz_warmwasser_grund).toBe('Strom nicht getrennt je Funktion gemessen')
    expect(d.wp_jaz_kuehlen_grund).toBe('kein Kühlbetrieb in diesem Zeitraum')
  })

  it('DER WÄCHTER: keine der drei Funktionen kommt ohne jede Auskunft an', () => {
    // Genau der Zustand, den der Tagespfad bis zum 29.08. lieferte: weder Wert
    // noch Grund. Die Fabrik rendert dann nichts — die Zeile verschwindet
    // lautlos, und das ist der Fund. Diese Probe prüft die **Regel** statt
    // dreier Feldnamen; eine vierte Funktion wäre damit mitgedeckt.
    const d = tagMit({
      wp_jaz_heizen: 4.0, wp_jaz_heizen_grund: null,
      wp_jaz_warmwasser: 2.0, wp_jaz_warmwasser_grund: null,
      wp_jaz_kuehlen: null,
      wp_jaz_kuehlen_grund: 'kein Kühlbetrieb in diesem Zeitraum',
    })

    for (const funktion of ['heizen', 'warmwasser', 'kuehlen'] as const) {
      const wert = d[`wp_jaz_${funktion}`]
      const grund = d[`wp_jaz_${funktion}_grund`]
      expect(
        wert != null || !!grund,
        `wp_jaz_${funktion}: weder Wert noch Grund erreicht die Fabrik — ` +
        `die Zeile verschwindet in der Tagessicht lautlos (N-348/S3)`,
      ).toBe(true)
    }
  })
})
