import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { wpFunktionsGruppen, zeigtStromJeFunktion } from './wpFunktionsGruppen'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import { baueTagAlsMonat } from './TagKomponenten'
import type { ParkApi } from '../components/park'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import type { TagDetail } from '../api/energie_profil'
import { aktuellerMonat, tagWerte } from '../test/factories'

/**
 * Bauschnitt 8 — die Detail-Liste des Wärme/Klima-Blocks **je Funktion**
 * (Konzept Wärme/Klima §4 ②; Bauplan `bauplan-waerme-klima-bs8-funktions-gruppen.md`).
 *
 * Geprüft wird an **Einzelwerten**, nicht an Zeilenzahlen: eine Gruppe mit der
 * richtigen Anzahl Zeilen, aber vertauschten Mengen, wäre sonst grün.
 */

const NOOP: ParkApi = {
  aktiv: false, istGeparkt: () => false, park: () => {}, entparke: () => {},
  zuruecksetzen: () => {}, geparkt: [], registriere: () => () => {}, parkbareAnzahl: 0,
}

const d = (over: Partial<AktuellerMonatResponse>) => aktuellerMonat(2026, 8, over)

/** F5 + Wärmemengenzähler je Funktion + Betriebsart Kühlen mit Kältezähler. */
const VOLL: Partial<AktuellerMonatResponse> = {
  wp_strom_kwh: 1300, wp_waerme_kwh: 3600,
  wp_strom_heizen_kwh: 750, wp_strom_warmwasser_kwh: 250,
  wp_heizung_kwh: 3000, wp_warmwasser_kwh: 600,
  wp_jaz_heizen: 4.0, wp_jaz_warmwasser: 2.4,
  wp_modus_strom_kuehlen_kwh: 300, wp_kaelte_kwh: 900, wp_jaz_kuehlen: 3.0,
}

describe('wpFunktionsGruppen — je Funktion Strom · Nutzenergie · Arbeitszahl', () => {
  it('ordnet Heizen · Warmwasser · Kühlen, jede Gruppe mit ihren eigenen Mengen', () => {
    const fg = wpFunktionsGruppen(d(VOLL))

    expect(fg.gruppen.map((g) => g.funktion)).toEqual(['heizen', 'warmwasser', 'kuehlen'])
    expect(fg.gruppen[0].zeilen).toEqual([
      { art: 'strom', label: 'Strom Heizen', kwh: 750 },
      { art: 'nutzenergie', label: 'Heizwärme', kwh: 3000 },
      { art: 'arbeitszahl', label: 'Arbeitszahl · Heizen', wert: 4.0 },
    ])
    expect(fg.gruppen[1].zeilen).toEqual([
      { art: 'strom', label: 'Strom Warmwasser', kwh: 250 },
      { art: 'nutzenergie', label: 'Warmwasser-Wärme', kwh: 600 },
      { art: 'arbeitszahl', label: 'Arbeitszahl · Warmwasser', wert: 2.4 },
    ])
    // Die Zeile „Kälte" (Entscheid E4 (a)) — Zähler und Nenner der Kühlzahl.
    expect(fg.gruppen[2].zeilen).toEqual([
      { art: 'strom', label: 'Strom Kühlen', kwh: 300 },
      { art: 'nutzenergie', label: 'Kälte', kwh: 900 },
      { art: 'arbeitszahl', label: 'Arbeitszahl · Kühlen', wert: 3.0 },
    ])
  })

  it('Split-Klima: keine Überschrift „Warmwasser" — die Funktion gibt es dort nicht (G7)', () => {
    const fg = wpFunktionsGruppen(d({
      wp_strom_kwh: 200, wp_modus_strom_heizen_kwh: 120, wp_modus_strom_kuehlen_kwh: 80,
      wp_jaz_heizen: null, wp_jaz_heizen_grund: 'Strom nicht getrennt je Funktion gemessen',
      wp_jaz_warmwasser: null, wp_jaz_warmwasser_grund: 'Strom nicht getrennt je Funktion gemessen',
      wp_jaz_kuehlen: null, wp_jaz_kuehlen_grund: 'kein Kältemengenzähler zugeordnet',
    }))

    expect(fg.gruppen.map((g) => g.funktion)).toEqual(['kuehlen'])
    // ⭐ **Wortlaut umgestellt, Substanz gehalten (D-Sicht, 14.09.2026).**
    // Geprüft war: *„die Gründe stehen als Einzelzeilen"* — zwei Zeilen aus
    // Strichen, die beide denselben fehlenden Zähler nannten. Die Auskunft geht
    // nicht verloren, sie wandert: Der Grund steht **einmal** im Kasten „Was
    // noch möglich wäre", mit dem Handgriff daneben (`wp_moeglich`). Ohne
    // Kasten-Angabe bleibt die Zeile — dieser Fall misst genau das.
    expect(fg.gruppen.length).toBe(1)
  })

  it('Heiz-WP im Winter: Kühlstrom 0 ergibt keine Gruppe „Kühlen", nur die Grund-Zeile', () => {
    const fg = wpFunktionsGruppen(d({
      ...VOLL, wp_modus_strom_kuehlen_kwh: 0, wp_kaelte_kwh: null,
      wp_jaz_kuehlen: null, wp_jaz_kuehlen_grund: 'kein Kühlbetrieb in diesem Zeitraum',
    }))

    // D-Sicht: „kein Kühlbetrieb in diesem Zeitraum" ist ein **Zeitraum**-Grund
    // — er legt nichts in den Kasten, und ohne Menge hat die Zeile nichts mehr
    // zu sagen. Sie entfällt; die Gruppen der beiden anderen Funktionen bleiben.
    expect(fg.gruppen.map((g) => g.funktion)).toEqual(['heizen', 'warmwasser'])
  })

  it('eine gemessene 0 bleibt in ihrer Gruppe stehen — sie ist nicht „nicht erfasst"', () => {
    const fg = wpFunktionsGruppen(d({ ...VOLL, wp_strom_warmwasser_kwh: 0 }))
    expect(fg.gruppen[1].zeilen[0]).toEqual({ art: 'strom', label: 'Strom Warmwasser', kwh: 0 })
  })

  it('ohne Wert UND ohne Grund keine Arbeitszahl-Zeile (N-348 bleibt)', () => {
    const fg = wpFunktionsGruppen(d({ ...VOLL, wp_jaz_heizen: null, wp_jaz_heizen_grund: null }))
    expect(fg.gruppen[0].zeilen.map((z) => z.art)).toEqual(['strom', 'nutzenergie'])
  })

  it('E3: nur ein getrennt gemessener Strom (F5) zählt als „Strom je Funktion"', () => {
    expect(zeigtStromJeFunktion(wpFunktionsGruppen(d(VOLL)))).toBe(true)
    // Kühlstrom ist Betriebsart = Funktion — er macht den Balken-Titel nicht mehrdeutig.
    expect(zeigtStromJeFunktion(wpFunktionsGruppen(d({
      wp_strom_kwh: 200, wp_modus_strom_kuehlen_kwh: 80,
    })))).toBe(false)
  })
})

describe('Der Block — Liste je Funktion statt Wärme-Balken (E1 (b)), Titel nach E3 (b)', () => {
  function rendereWp(over: Partial<AktuellerMonatResponse>) {
    const block = baueKomponentenBloecke(d(over), NOOP, 'monat').find((b) => b.id === 'k-waermepumpe')
    expect(block, 'Wärme/Klima-Block muss entstehen').toBeDefined()
    render(<>{block!.render(false)}</>)
  }

  it('zeigt die Gruppen samt Kälte, der Wärme-Balken ist entfallen', () => {
    rendereWp(VOLL)
    expect(screen.getByText('Je Funktion')).toBeInTheDocument()
    expect(screen.getByText('Kälte')).toBeInTheDocument()
    expect(screen.getByText('900 kWh')).toBeInTheDocument()
    expect(screen.queryByText('Wärme-Aufteilung')).toBeNull()
  })

  it('mit F5 und Betriebsart-Aufteilung heißt der Balken „nach Betriebsart"', () => {
    rendereWp({ ...VOLL, wp_modus_strom_heizen_kwh: 1000, wp_modus_abdeckung_h: 700 })
    expect(screen.getByText('Strom-Aufteilung nach Betriebsart')).toBeInTheDocument()
    expect(screen.queryByText('Strom-Aufteilung Heizen/Kühlen')).toBeNull()
  })

  it('ohne F5 bleibt der eingeführte Titel', () => {
    rendereWp({
      wp_strom_kwh: 200, wp_modus_strom_heizen_kwh: 120, wp_modus_strom_kuehlen_kwh: 80,
      wp_modus_abdeckung_h: 700,
    })
    expect(screen.getByText('Strom-Aufteilung Heizen/Kühlen')).toBeInTheDocument()
  })
})

describe('Die Kälte erreicht den Tag (das Jahr: Backend-Probe)', () => {
  it('Tag: baueTagAlsMonat reicht die Kältemenge der Tagesantwort durch', () => {
    const tag = baueTagAlsMonat(
      tagWerte('2026-08-29', { wp_strom: 30.0 }), [], [],
      { wp_kaelte_kwh: 18 } as TagDetail,
    )
    expect(tag.wp_kaelte_kwh).toBe(18)
  })

  // Die drei Jahr-Proben (Kälte aus der Route · Route sagt „keine" · Rückfall Σ ohne Route) sind mit der Faltung
  // ins Backend gezogen: `backend/tests/test_ergebnis_jahr_portiert.py::test_kaelte_aus_der_route_oder_summe`
  // (dieselben Zahlen 400/500 → 888 · null · 900).
})
