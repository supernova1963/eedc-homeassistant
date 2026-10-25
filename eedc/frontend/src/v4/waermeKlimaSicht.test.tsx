import { describe, it, expect } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import {
  ACHSE, GROESSE, geraetZelle, imKasten, jazAnzeige, kennzahlUntertitel,
} from './waermeKlimaSicht'
import type { ParkApi } from '../components/park'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import { aktuellerMonat } from '../test/factories'

/**
 * **D-Sicht + E1b im Block** — die Client-Hälfte von WK-16ab.
 *
 * *„Das release ich so nicht."* (Gernot, 14.09.2026): Cockpit → Monat bestand im
 * Block *Wärme/Klima* aus vier Strichen mit Grund-Texten. Seither gilt:
 *
 * * Kacheln und Zeilen **nur mit Zahl**.
 * * Was die **Ausstattung** nicht hergibt, steht **einmal** im Kasten
 *   *„Was noch möglich wäre"* — mit dem Handgriff daneben.
 * * Was die Ausstattung hergibt und in **diesem Zeitraum** leer ist, bleibt ein
 *   „—" **ohne Text**.
 * * Die anlagenweite Zahl darf eine untere **Schranke** sein: „≥ 3,0".
 *
 * ⛔ **Der Client klassifiziert nicht.** Ob ein Grund zur Ausstattung gehört,
 * entscheidet der Layer; hier wird nur abgefragt, was im Kasten steht — und
 * zwar über den **Größen-Namen**, nicht über den Grund-Text (die Tages-Route
 * reicht an derselben Kachel Kurz- und Langform verschieden herein).
 *
 * Schwesterdateien: `KomponentenSektionen.soll-waerme-klima.test.tsx` (S3),
 * `KomponentenSektionen.tag-arbeitszahl.test.tsx` (N-348),
 * Backend `test_wk16_e1b_d_sicht.py`.
 */

const NOOP: ParkApi = {
  aktiv: false, istGeparkt: () => false, park: () => {}, entparke: () => {},
  zuruecksetzen: () => {}, geparkt: [], registriere: () => () => {}, parkbareAnzahl: 0,
}

const d = (over: Partial<AktuellerMonatResponse> = {}) => aktuellerMonat(2026, 8, over)

function rendere(over: Partial<AktuellerMonatResponse>, periode: 'monat' | 'tag' = 'monat') {
  const block = baueKomponentenBloecke(d(over), NOOP, periode)
    .find((b) => b.id === 'k-waermepumpe')
  expect(block, 'Wärme/Klima-Block muss entstehen').toBeDefined()
  render(<>{block!.render(false)}</>)
  return block!
}

/** Die Lage des Melders: Wärmepumpe + Split-Klimaanlage, anlagenweit ≥ 3,0. */
const MELDER: Partial<AktuellerMonatResponse> = {
  wp_strom_kwh: 1000, wp_waerme_kwh: 3000,
  wp_jaz: 3.0, wp_jaz_ist_schranke: true,
  wp_jaz_schranke_hinweis: 'Klimaanlage: Strom ohne Wärmemessung enthalten',
  wp_jaz_zaehler_kwh: 3000, wp_jaz_nenner_kwh: 1000,
  wp_geraete: [
    { investition_id: 1, name: 'Wärmepumpe', strom_kwh: 800, waerme_kwh: 3000, jaz: 3.75 },
    { investition_id: 2, name: 'Klimaanlage', strom_kwh: 200, waerme_kwh: null, jaz: null },
  ],
}

/** P-433-3 S3: ein einzelnes Gerät für die Probe «bei einem Gerät keine Tabelle». */
const ZWEITGERAET_EINZELN = {
  investition_id: 98, name: 'Einzelgerät', strom_kwh: 10, waerme_kwh: 30, jaz: 3,
  jaz_heizen: null, jaz_heizen_grund: null, jaz_warmwasser: null, jaz_warmwasser_grund: null,
}

describe('waermeKlimaSicht — die reinen Regeln', () => {
  it('jazAnzeige setzt „≥" nur vor eine Schranke', () => {
    expect(jazAnzeige(3.25, true, '3,25')).toBe('≥ 3,25')
    expect(jazAnzeige(3.25, false, '3,25')).toBe('3,25')
    // ⛔ Ohne Wert kein Zeichen — „≥ —" wäre keine Aussage.
    expect(jazAnzeige(null, true, '—')).toBe('—')
  })

  it('kennzahlUntertitel trägt Schranke UND Heizstab, nie einen Grund', () => {
    expect(kennzahlUntertitel(1.5, 'Klima: Strom ohne Wärmemessung enthalten', 'Heizstab-Satz'))
      .toBe('Klima: Strom ohne Wärmemessung enthalten · Heizstab-Satz')
    // ⛔ Ohne Wert gibt es keinen Untertitel: Der Grund steht im Kasten
    // (Ausstattung) oder es gibt nichts zu tun (Zeitraum).
    expect(kennzahlUntertitel(null, null, null)).toBeUndefined()
  })

  it('imKasten fragt über den GRÖSSEN-NAMEN, nicht über den Grund-Text', () => {
    const moeglich = [{
      groessen: ['Arbeitszahl Heizen', 'Arbeitszahl Warmwasser'],
      groesse: 'Arbeitszahl Heizen · Arbeitszahl Warmwasser',
      grund: 'Strom nicht getrennt je Funktion gemessen',
    }]
    expect(imKasten(moeglich, GROESSE.heizen)).toBe(true)
    expect(imKasten(moeglich, GROESSE.kuehlen)).toBe(false)
    expect(imKasten(undefined, GROESSE.heizen)).toBe(false)
  })

  it('die Bezeichner sind der Vertrag mit dem Backend', () => {
    // ⚠ Spiegel von `services/waerme_klima_block.py::GROESSEN_IM_KASTEN`,
    // festgehalten auf beiden Seiten (dort `test_die_groessen_namen_sind_der_vertrag`).
    expect(Object.values(GROESSE).sort()).toEqual([
      'Arbeitszahl', 'Arbeitszahl Heizen', 'Arbeitszahl Kühlen',
      'Arbeitszahl Warmwasser', 'Wärme erzeugt',
    ])
  })
})

describe('E1b — die Schranke im Block', () => {
  it('die Kachel zeigt „≥ 3,00" und nennt den Grund der Schranke', () => {
    rendere(MELDER)
    expect(screen.getByText('≥ 3,00')).toBeInTheDocument()
    expect(screen.getByText(/Strom ohne Wärmemessung enthalten/)).toBeInTheDocument()
  })

  it('ohne Schranke steht die Zahl nackt da — Gegenprobe', () => {
    // ⛔ Ohne diesen Fall wäre nicht gezeigt, dass das Zeichen am **Flag** hängt.
    // Eine Fassung, die immer „≥" setzt, wäre oben ebenso grün — und behauptete
    // an jeder sauber messenden Anlage eine Unsicherheit, die es nicht gibt.
    rendere({ ...MELDER, wp_jaz_ist_schranke: false, wp_jaz_schranke_hinweis: null })
    expect(screen.getByText('3,00')).toBeInTheDocument()
    expect(screen.queryByText('≥ 3,00')).toBeNull()
  })
})

describe('D-Sicht — Kacheln und Zeilen nur mit Zahl', () => {
  const GRUND = 'kein Kältemengenzähler zugeordnet'

  it('der Kasten listet jeden Ausstattungs-Grund genau einmal, mit Handgriff', () => {
    rendere({
      ...MELDER,
      wp_jaz_kuehlen: null, wp_jaz_kuehlen_grund: GRUND,
      wp_modus_strom_kuehlen_kwh: 40,
      wp_moeglich: [{
        groessen: ['Arbeitszahl Kühlen'], groesse: 'Arbeitszahl Kühlen',
        grund: GRUND, handgriff: 'Kältemengenzähler zuordnen',
        link: '#/einstellungen/datenquellen',
      }],
    })

    expect(screen.getByText('Was noch möglich wäre')).toBeInTheDocument()
    expect(screen.getAllByText(GRUND)).toHaveLength(1)
    expect(screen.getByText('Kältemengenzähler zuordnen')).toBeInTheDocument()
    // Der Weg dorthin — der Kasten verweist, er wiederholt den Daten-Checker nicht.
    expect(screen.getByText('Kältemengenzähler zuordnen').closest('a'))
      .toHaveAttribute('href', '#/einstellungen/datenquellen')
  })

  it('eine Kachel ohne Zahl verschwindet, wenn ihr Grund im Kasten steht', () => {
    rendere({
      wp_strom_kwh: 1000, wp_waerme_kwh: null,
      wp_jaz: null, wp_jaz_grund: 'kein Wärmemengenzähler zugeordnet',
      wp_moeglich: [{
        groessen: ['Arbeitszahl'], groesse: 'Arbeitszahl',
        grund: 'kein Wärmemengenzähler zugeordnet',
      }],
    })

    // Die JAZ-Kachel ist weg — ihr Titel steht nirgends mehr.
    expect(screen.queryByText('JAZ')).toBeNull()
    // Die Mengen bleiben: gesperrt wird eine Kennzahl, nie eine Messung (K1).
    expect(screen.getByText('1.000')).toBeInTheDocument()
  })

  it('ein Zeitraum-Grund lässt die Kachel stehen — „—" ohne Text', () => {
    // ⛔ **Die Gegenprobe, und ohne sie misst die Probe darüber nichts.** Eine
    // Fassung, die jede wertlose Kachel entfernt, wäre dort ebenso grün — und
    // im Juni fehlte die Heizzahl ganz, statt zu sagen „in diesem Zeitraum
    // nichts". Der Unterschied hängt allein am Kasten-Eintrag.
    rendere({
      wp_strom_kwh: 1000, wp_waerme_kwh: null,
      wp_jaz: null, wp_jaz_grund: 'kein Heizbetrieb in diesem Zeitraum',
      wp_moeglich: [],
    })

    expect(screen.getByText('JAZ')).toBeInTheDocument()
    expect(screen.queryByText('kein Heizbetrieb in diesem Zeitraum')).toBeNull()
  })

  it('ohne Kasten-Zeilen erscheint der Kasten gar nicht', () => {
    rendere(MELDER)
    expect(screen.queryByText('Was noch möglich wäre')).toBeNull()
  })
})

describe('D-Sicht 2 — der Strich nennt seinen Zeitraum-Grund beim Überfahren', () => {
  /**
   * ⭐ **Entscheid Fable (14.09.2026), Gegenlesung zu A-4.** Ein Zeitraum-Grund
   * gehört in keinen Kasten — es gibt nichts zu tun —, aber er soll auch nicht
   * verschwinden: **S3 bleibt erfüllt, wenn der Grund eine Geste entfernt ist.**
   * Sichtbar bleibt der Block trotzdem frei von Texten.
   *
   * ⚠ **Zwei Träger, und das ist Regel 0a, kein Versehen:** Die **Kachel** hat
   * für genau diesen Fall einen SoT-Slot (`KpiStripItem.hinweis` →
   * `SimpleTooltip`), die Detail-**Zeilen** haben keinen — dort steht das native
   * `title`, wie an den Balken in `SpeicherPotentialIST`. Eine zweite
   * Tooltip-Bauform neben der bestehenden wäre der Fehler.
   */
  const ZEITRAUM = 'kein Heizbetrieb in diesem Zeitraum'
  const AUSSTATTUNG = 'Strom nicht getrennt je Funktion gemessen'

  /** Der Wert-Träger einer Funktionszeile (das `<dd>` neben dem Label). */
  const zeileWert = (label: string) =>
    screen.getByText(label).parentElement?.querySelector('dd')

  it('Zeitraum-Grund: die Zeile zeigt „—" und trägt ihn als title', () => {
    rendere({
      ...MELDER,
      wp_strom_heizen_kwh: 750, wp_heizung_kwh: 3000,
      wp_jaz_heizen: null, wp_jaz_heizen_grund: ZEITRAUM,
      wp_moeglich: [],
    })

    const dd = zeileWert('Arbeitszahl · Heizen')
    expect(dd?.textContent).toBe('—')
    expect(dd).toHaveAttribute('title', ZEITRAUM)
    // ⛔ **Und NICHT sichtbar** — sonst wäre die D-Sicht zurückgedreht.
    expect(screen.queryByText(ZEITRAUM)).toBeNull()
  })

  it('Ausstattungs-Grund: kein title — der Grund steht einmal im Kasten', () => {
    // ⛔ **Die Gegenprobe, und ohne sie misst die Probe darüber nichts.** Eine
    // Fassung, die JEDEN Grund als `title` anhängt, wäre dort ebenso grün — und
    // der Ausstattungs-Grund stünde dann zweimal: im Kasten und am Strich.
    rendere({
      ...MELDER,
      wp_strom_heizen_kwh: 750, wp_heizung_kwh: 3000,
      wp_jaz_heizen: null, wp_jaz_heizen_grund: AUSSTATTUNG,
      wp_moeglich: [{
        groessen: ['Arbeitszahl Heizen'], groesse: 'Arbeitszahl Heizen',
        grund: AUSSTATTUNG, handgriff: 'Getrennte Strommessung einschalten',
      }],
    })

    // Die Zeile ist weg — ihr Grund steht im Kasten, mit dem Handgriff.
    expect(screen.queryByText('Arbeitszahl · Heizen')).toBeNull()
    expect(screen.getAllByText(AUSSTATTUNG)).toHaveLength(1)
    expect(screen.getByText('Getrennte Strommessung einschalten')).toBeInTheDocument()
  })

  it('eine Zeile MIT Zahl trägt keinen title — es gibt nichts zu erklären', () => {
    // ⚠ **Diese Probe ist NICHT diskriminierend, und das steht hier, statt es
    // zu verschweigen** (gemessen 14.09.): Ein Sprengsatz, der den Riegel
    // `azWert == null` entfernt, bleibt grün — der Layer setzt **Wert ODER
    // Grund**, nie beides, also gibt es in dieser Lage gar keinen Grund
    // anzuhängen. Sie hält den **Vertrag** fest (eine Zahl erklärt sich
    // selbst), nicht den Riegel; ein Fixture mit beidem wäre ein produktiv
    // unerreichbarer Zustand.
    rendere({
      ...MELDER,
      wp_strom_heizen_kwh: 750, wp_heizung_kwh: 3000, wp_jaz_heizen: 4.0,
      wp_moeglich: [],
    })

    const dd = zeileWert('Arbeitszahl · Heizen')
    expect(dd?.textContent).toBe('4,00')
    expect(dd).not.toHaveAttribute('title')
  })

  it('die JAZ-Kachel nennt ihren Zeitraum-Grund beim Überfahren', () => {
    rendere({
      wp_strom_kwh: 1000, wp_waerme_kwh: null,
      wp_jaz: null, wp_jaz_grund: ZEITRAUM,
      wp_moeglich: [],
    })

    // Vor der Geste steht der Grund nirgends.
    expect(screen.queryByText(ZEITRAUM)).toBeNull()
    fireEvent.mouseEnter(screen.getAllByText('—')[0])
    expect(screen.getByText(ZEITRAUM)).toBeInTheDocument()
  })
})

describe('D-Sicht 3 — die Tabelle „Zahlen je Gerät" steht im Block', () => {
  it('nennt jedes Gerät mit seiner eigenen Zahl', () => {
    rendere(MELDER)

    expect(screen.getByText('Zahlen je Gerät')).toBeInTheDocument()
    expect(screen.getByText('Wärmepumpe')).toBeInTheDocument()
    expect(screen.getByText('3,75')).toBeInTheDocument()
    expect(screen.getByText('Klimaanlage')).toBeInTheDocument()
    // ⛔ **Eine Klimaanlage ohne Wärmemessung bekommt keine Zahl** — auch nicht
    // über die Anlagensumme. E1 gilt je Gerät unverändert.
    expect(screen.getByText('200')).toBeInTheDocument()
  })

  it('ohne Geräte-Zeilen gibt es die Tabelle nicht', () => {
    rendere({ ...MELDER, wp_geraete: [] })
    expect(screen.queryByText('Zahlen je Gerät')).toBeNull()
  })

  it('P-433-3 S3 (E-P3-6): bei EINEM Gerät gibt es die Tabelle nicht — der Link in den Hub bleibt', () => {
    rendere({ ...MELDER, wp_geraete: [{ ...ZWEITGERAET_EINZELN }] })
    expect(screen.queryByText('Zahlen je Gerät')).toBeNull()
    expect(screen.getByText(/im Komponenten-Hub/)).toBeInTheDocument()
  })
})

/**
 * **WK-16h — kein Strich ohne Grund, keine Kachel ohne Zahl** (N-500 · N-502).
 *
 * Gemessen an der r28 am 15.09.2026: Im Block *Wärme/Klima* stand **kein
 * einziges** `title` — jede Zelle ohne Zahl war ein unerklärter Strich, obwohl
 * die API je Zelle einen Grund liefert. Und die Kachel *„Ersparnis vs.
 * Alternative"* stand in *Cockpit → Tag* an jedem geprüften Tag als „—": Der
 * Tag rechnet keine Ersparnis, das Feld gibt es in `tag-detail` gar nicht.
 */
/** P-433-3 S3 (E-P3-6): die Tabelle «Zahlen je Gerät» erscheint erst ab ZWEI Geräten — die Zellen-Proben unten
 *  tragen deshalb ein zweites, unauffälliges Gerät mit; ihre Aussagen über die Zellen sind unverändert. */
const ZWEITGERAET = {
  investition_id: 99, name: 'Zweitgerät', strom_kwh: 10, waerme_kwh: 30, jaz: 3,
  jaz_heizen: null, jaz_heizen_grund: null, jaz_warmwasser: null, jaz_warmwasser_grund: null,
}

describe('WK-16h — die Zelle der Tabelle', () => {
  it('geraetZelle: Zahl ohne title, Strich mit Grund, fehlende Achse leer', () => {
    const bosch = {
      investition_id: 2, name: 'Bosch', achsen: ['heizen'],
      jaz_heizen_grund: 'kein Wärmemengenzähler zugeordnet',
      jaz_warmwasser_grund: null,
    }
    // Eine Zahl erklärt sich selbst.
    expect(geraetZelle(3.75, null)).toEqual({ leer: false })
    // Kein Wert, Achse gilt ⇒ der Grund wird zum Tooltip.
    expect(geraetZelle(null, bosch.jaz_heizen_grund, ACHSE.heizen, bosch))
      .toEqual({ leer: false, title: 'kein Wärmemengenzähler zugeordnet' })
    // ⛔ Achse gilt nicht ⇒ gar nichts: kein Strich, kein Tooltip.
    expect(geraetZelle(null, null, ACHSE.warmwasser, bosch)).toEqual({ leer: true })
  })

  it('eine Zelle ohne Zahl trägt den Grund als title — eine mit Zahl nicht', () => {
    rendere({
      ...MELDER,
      wp_geraete: [{
        investition_id: 2, name: 'Bosch Multisplit', strom_kwh: 200,
        waerme_kwh: null, jaz: null,
        waerme_grund: 'kein Wärmemengenzähler zugeordnet',
        jaz_grund: 'kein Wärmemengenzähler zugeordnet',
        jaz_heizen: null, jaz_heizen_grund: 'kein Wärmemengenzähler zugeordnet',
        jaz_warmwasser: null, jaz_warmwasser_grund: null,
        jaz_kuehlen: null, jaz_kuehlen_grund: 'kein Kältemengenzähler zugeordnet',
        achsen: ['heizen'],
      }, ZWEITGERAET],
    })
    const zeile = screen.getByText('Bosch Multisplit').closest('tr')!
    const zellen = [...zeile.querySelectorAll('td')]
    // Gerät · Wärme · Strom · Arbeitszahl · Heizen · Warmwasser · Kühlen
    expect(zellen[3].getAttribute('title')).toBe('kein Wärmemengenzähler zugeordnet')
    expect(zellen[4].getAttribute('title')).toBe('kein Wärmemengenzähler zugeordnet')
    expect(zellen[6].getAttribute('title')).toBe('kein Kältemengenzähler zugeordnet')
    // ⛔ Die Warmwasser-Spalte einer Klimaanlage bleibt LEER — kein Strich,
    // kein Tooltip. „Gilt nicht" ist kein Mangel.
    expect(zellen[5].textContent).toBe('')
    expect(zellen[5].getAttribute('title')).toBeNull()
    // Die Mengen erklären sich selbst — solange sie eine Zahl sind. Die leere
    // Wärme-Zelle trägt ihren Grund wie jede andere (R-4).
    expect(zellen[2].getAttribute('title')).toBeNull()
    expect(zellen[1].textContent).toBe('—')
    expect(zellen[1].getAttribute('title')).toBe('kein Wärmemengenzähler zugeordnet')
  })

  it('Gegenprobe: eine geltende Achse ohne Zahl zeigt den Strich', () => {
    rendere({
      ...MELDER,
      wp_geraete: [{
        investition_id: 1, name: 'Daikin', strom_kwh: 800, waerme_kwh: 3000,
        jaz: 3.75, jaz_heizen: null,
        jaz_heizen_grund: 'kein Heizbetrieb in diesem Zeitraum',
        jaz_warmwasser: null, jaz_warmwasser_grund: null,
        achsen: ['heizen', 'warmwasser'],
      }, ZWEITGERAET],
    })
    const zellen = [...screen.getByText('Daikin').closest('tr')!.querySelectorAll('td')]
    expect(zellen[4].textContent).toBe('—')
    expect(zellen[4].getAttribute('title')).toBe('kein Heizbetrieb in diesem Zeitraum')
    // Warmwasser gilt, hat aber weder Zahl noch Grund ⇒ Strich ohne title.
    expect(zellen[5].textContent).toBe('—')
    expect(zellen[5].getAttribute('title')).toBeNull()
  })

  it('ohne `achsen` bleibt jede Spalte stehen — Altbestand einer Antwort', () => {
    rendere({
      ...MELDER,
      wp_geraete: [{
        investition_id: 1, name: 'Altbestand', strom_kwh: 800, waerme_kwh: 3000,
        jaz: 3.75, jaz_warmwasser: null,
        jaz_warmwasser_grund: 'Wärme nicht je Funktion gemessen',
      }, ZWEITGERAET],
    })
    const zellen = [...screen.getByText('Altbestand').closest('tr')!.querySelectorAll('td')]
    expect(zellen[5].textContent).toBe('—')
    expect(zellen[5].getAttribute('title')).toBe('Wärme nicht je Funktion gemessen')
  })
})

describe('WK-16h — die Ersparnis-Kachel erscheint nur mit Wert', () => {
  it('Cockpit → Tag: ohne Betrag gibt es die Kachel nicht', () => {
    rendere({ ...MELDER, wp_ersparnis_euro: null }, 'tag')
    expect(screen.queryByText('Ersparnis vs. Alternative')).toBeNull()
    // ⛔ Und KEINE Kasten-Zeile: Der Kasten nennt Ausstattung, an der man etwas
    // ändern kann — hier fehlt kein Zähler, sondern eine Rechnung in dieser Sicht.
    expect(screen.queryByText(/Ersparnis/)).toBeNull()
  })

  it('Gegenprobe: mit Betrag steht sie da', () => {
    rendere({ ...MELDER, wp_ersparnis_euro: 58.07 }, 'monat')
    expect(screen.getByText('Ersparnis vs. Alternative')).toBeInTheDocument()
  })

  it('auch im Monat verschwindet sie ohne Betrag — D-Sicht 1 gilt je Sicht', () => {
    rendere({ ...MELDER, wp_ersparnis_euro: null }, 'monat')
    expect(screen.queryByText('Ersparnis vs. Alternative')).toBeNull()
  })
})
