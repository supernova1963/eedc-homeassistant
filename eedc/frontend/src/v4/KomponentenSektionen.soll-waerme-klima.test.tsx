import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import type { ParkApi } from '../components/park'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import { aktuellerMonat } from '../test/factories'

/**
 * SOLL Wärme/Klima — **Achse III-3 (Balken sagen ihre Größe) und Achse IV (Aussage)**.
 *
 * Maschinelle Fassung von `soll-waerme-klima.md` §3.3/**S2** und §4.3.
 * Schwesterdatei zu `KomponentenSektionen.test.tsx` (dort das Aktiv-Gating).
 *
 * ## Zwei Sorten von Proben, bewusst getrennt
 *
 * Dieselbe Bauform wie die Backend-Achsen (`test_soll_waerme_klima_achse*.py`):
 *
 * - **ERFÜLLT** — die SOLL-Erwartung ist gebaut. Harte Assertion.
 * - **OFFEN** — der Bauschritt steht aus. Die Probe hält den **heutigen**
 *   Zustand fest und nennt den Soll-Zustand. Wird gebaut, **schlägt sie fehl**
 *   — sie ist dann umzustellen und ihr Eintrag aus `REGELN_OFFEN` zu entfernen.
 *
 * Eine fehlschlagende OFFEN-Probe ist kein Alarm, sondern eine Quittung.
 */

/** SOLL-Regeln, die noch **nicht** gebaut sind. */
const REGELN_OFFEN: Record<string, string> = {
  'S2/W-8': 'Wärme-Aufteilung und Strom-Aufteilung nehmen unbeschriftet denselben '
    + 'Platz ein. Die Element-Titel gehen nur an die Park-Chips (Parkbar.tsx:78), '
    + 'nicht in die Anzeige. Melder dietmar1968 (T89667 #203).',
  '§4.3/W-10': 'Ein Minusbetrag erscheint mit vorangestelltem Plus unter der '
    + 'Überschrift „Ersparnis" — „+−49,53 €". Zwei Melder-Screenshots (25.08.).',
  '§2.2.1/W-6': 'Eine Arbeitszahl unter etwa 2 steht ohne ein Wort daneben. '
    + 'SOLL: eedc repariert Fall H-B nicht, es erklärt ihn.',
}

const NOOP: ParkApi = {
  aktiv: false, istGeparkt: () => false, park: () => {}, entparke: () => {},
  zuruecksetzen: () => {}, geparkt: [], registriere: () => () => {}, parkbareAnzahl: 0,
}

const d = (over: Partial<AktuellerMonatResponse> = {}) => aktuellerMonat(2026, 8, over)

/** Den Wärme/Klima-Block bauen und rendern. */
function rendereWpBlock(over: Partial<AktuellerMonatResponse>) {
  const block = baueKomponentenBloecke(d(over), NOOP, 'monat')
    .find((b) => b.id === 'k-waermepumpe')
  expect(block, 'Wärme/Klima-Block muss entstehen').toBeDefined()
  render(<>{block!.render(false)}</>)
  return block!
}

// ══ IV-1 · OFFEN — ein Minusbetrag mit vorangestelltem Plus ═════════════════

describe('Achse IV — die Zahl sagt, was sie ist', () => {
  it('OFFEN (§4.3/W-10): negative Ersparnis erscheint als „+−"', () => {
    expect(REGELN_OFFEN['§4.3/W-10']).toBeTruthy()
    rendereWpBlock({ wp_strom_kwh: 337, wp_waerme_kwh: 309, wp_ersparnis_euro: -49.53 })

    // SOLL: „Mehrkosten −49,53 €". Heute: das Plus wird unbesehen vorangestellt.
    //
    // ⚠ **Am gerenderten Text gemessen, nicht vom Screenshot abgeschrieben:**
    // Die Anzeige nutzt einen ASCII-Bindestrich (`+-49,53`), nicht das
    // typografische Minus `−`, das der Melder-Screenshot vermuten lässt. Ein
    // Test gegen das Bild statt gegen die Ausgabe wäre hier durchgefallen.
    expect(screen.getByText(/\+-49,53/)).toBeTruthy()
    expect(screen.queryByText(/Mehrkosten/)).toBeNull()
  })

  it('ERFÜLLT: eine positive Ersparnis trägt ihr Plus zu Recht', () => {
    // Gegenprobe — sie hält fest, was die Lösung von IV-1 nicht kaputt machen
    // darf. Der Fehler ist das UNBESEHENE Plus, nicht das Plus selbst.
    rendereWpBlock({ wp_strom_kwh: 500, wp_waerme_kwh: 2000, wp_ersparnis_euro: 312.4 })

    expect(screen.getByText(/\+312,40/)).toBeTruthy()
  })

  it('OFFEN (§2.2.1/W-6): eine Arbeitszahl unter 1 steht ohne ein Wort daneben', () => {
    expect(REGELN_OFFEN['§2.2.1/W-6']).toBeTruthy()
    // dietmars Juli: 309 kWh Wärme ÷ 337 kWh Strom = 0,92 — praktisch genau
    // das, was reiner Heizstab-Betrieb ergeben MUSS. Die Zahl ist richtig
    // (Fall H-B), es fehlt der Satz daneben.
    rendereWpBlock({ wp_strom_kwh: 337, wp_waerme_kwh: 309 })

    expect(screen.getByText('0,92')).toBeTruthy()
    // SOLL: sinngemäß „in diesem Zeitraum lief ein großer Teil über direkte
    // Elektroheizung". Heute steht dort nichts dergleichen.
    expect(screen.queryByText(/Heizstab|Elektroheizung|Zusatzheizung/i)).toBeNull()
  })

  it('ERFÜLLT: eine unauffällige Arbeitszahl braucht keinen Satz', () => {
    // Gegenprobe zur Schwelle: Der Hinweis aus W-6 darf nicht überall stehen,
    // sonst erklärt er nichts mehr. SOLL nennt „unter etwa 2".
    rendereWpBlock({ wp_strom_kwh: 500, wp_waerme_kwh: 2000 })

    expect(screen.getByText('4,00')).toBeTruthy()
    expect(screen.queryByText(/Heizstab|Elektroheizung/i)).toBeNull()
  })
})

// ══ III-3 · OFFEN — S2: zwei Größen teilen sich einen Balkenplatz ═══════════

describe('Achse III-3 — ein Balken sagt, was er zeigt', () => {
  it('OFFEN (S2/W-8): die Wärme-Aufteilung nennt ihre Größe nicht in der Anzeige', () => {
    expect(REGELN_OFFEN['S2/W-8']).toBeTruthy()
    // dietmars Juli-Bild: Balken „Heizung" / „Warmwasser" — das sind WÄRME-kWh.
    rendereWpBlock({
      wp_strom_kwh: 337, wp_waerme_kwh: 309,
      wp_heizung_kwh: 0, wp_warmwasser_kwh: 309,
    })

    expect(screen.getByText('Heizung')).toBeTruthy()
    expect(screen.getByText('Warmwasser')).toBeTruthy()
    // SOLL S2: „Wechselt der Inhalt je nach Datenlage, wechselt auch die
    // Beschriftung." Der Element-Titel „Wärme-Aufteilung" existiert, geht aber
    // nur an den Park-Chip — in der Anzeige steht er nicht.
    expect(screen.queryByText(/Wärme-Aufteilung/)).toBeNull()
  })

  it('OFFEN (S2/W-8): die Strom-Aufteilung nennt ihre Größe erst recht nicht', () => {
    expect(REGELN_OFFEN['S2/W-8']).toBeTruthy()
    // dietmars August-Bild: derselbe Platz, andere Bedeutung — das sind STROM-kWh.
    rendereWpBlock({
      wp_strom_kwh: 279, wp_waerme_kwh: 177,
      wp_modus_gemessen: true,
      wp_modus_strom_heizen_kwh: 1, wp_modus_strom_kuehlen_kwh: 3,
      wp_modus_nicht_aufgeteilt_kwh: 21,
    })

    expect(screen.getByText('Heizen')).toBeTruthy()
    expect(screen.getByText('Kühlen')).toBeTruthy()
    expect(screen.getByText('Nicht aufgeteilt')).toBeTruthy()
    // Nirgends steht, dass dieser Balken Strom zeigt.
    expect(screen.queryByText(/Strom-Aufteilung/)).toBeNull()
  })

  it('OFFEN (S2/W-8): derselbe Block zeigt in zwei Monaten zwei verschiedene Größen', () => {
    expect(REGELN_OFFEN['S2/W-8']).toBeTruthy()
    // Das ist dietmars Beschwerde in einem Test: „Warmwasser erscheint als
    // Balken gar nicht mehr." Beide Monate, dieselbe Anlage, dieselbe Fußzeile
    // „Aggregiert aus: Wärmepumpe · Klimaanlage" — verschiedene Balkensätze.
    const juli = baueKomponentenBloecke(d({
      wp_strom_kwh: 337, wp_waerme_kwh: 309,
      wp_heizung_kwh: 0, wp_warmwasser_kwh: 309,
    }), NOOP, 'monat').find((b) => b.id === 'k-waermepumpe')!

    const august = baueKomponentenBloecke(d({
      wp_strom_kwh: 279, wp_waerme_kwh: 177,
      wp_modus_gemessen: true,
      wp_modus_strom_heizen_kwh: 1, wp_modus_strom_kuehlen_kwh: 3,
      wp_modus_nicht_aufgeteilt_kwh: 21,
    }), NOOP, 'monat').find((b) => b.id === 'k-waermepumpe')!

    const { container: cJuli } = render(<>{juli.render(false)}</>)
    const { container: cAug } = render(<>{august.render(false)}</>)

    expect(cJuli.textContent).toContain('Warmwasser')
    // SOLL nach dem Bau: Der August-Balken sagt „Strom" und der Juli-Balken
    // „Wärme" — dann ist das Verschwinden erklärt statt rätselhaft.
    expect(cAug.textContent).not.toContain('Warmwasser')
  })
})
