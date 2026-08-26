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
  // Leer — alle Regeln dieser Datei sind gebaut (26.08.2026).
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
  it('ERFÜLLT (§4.3/W-10): ein negativer Betrag heißt Mehrkosten', () => {
    expect(REGELN_OFFEN['§4.3/W-10']).toBeUndefined()
    rendereWpBlock({ wp_strom_kwh: 337, wp_waerme_kwh: 309, wp_ersparnis_euro: -49.53 })

    // Vorher: „Ersparnis vs. Gas: **+-49,53 €**" — das Plus wurde unbesehen
    // vorangestellt. Zwei Melder-Screenshots (dietmar1968, 25.08.).
    //
    // ⚠ **Am gerenderten Text gemessen, nicht vom Screenshot abgeschrieben:**
    // Die Anzeige nutzt einen ASCII-Bindestrich, nicht das typografische Minus
    // `−`, das der Melder-Screenshot vermuten lässt. Ein Test gegen das Bild
    // statt gegen die Ausgabe wäre durchgefallen.
    expect(screen.queryByText(/\+-49,53/)).toBeNull()
    expect(screen.getByText('-49,53')).toBeTruthy()
    expect(screen.getByText('Mehrkosten vs. Gas')).toBeTruthy()
    expect(screen.queryByText('Ersparnis vs. Gas')).toBeNull()
  })

  it('ERFÜLLT: eine positive Ersparnis trägt ihr Plus zu Recht', () => {
    // Gegenprobe — sie hält fest, was die Lösung von IV-1 nicht kaputt machen
    // darf. Der Fehler ist das UNBESEHENE Plus, nicht das Plus selbst.
    rendereWpBlock({ wp_strom_kwh: 500, wp_waerme_kwh: 2000, wp_ersparnis_euro: 312.4 })

    expect(screen.getByText(/\+312,40/)).toBeTruthy()
    expect(screen.getByText('Ersparnis vs. Gas')).toBeTruthy()
  })

  it('ERFÜLLT (§2.2.1/W-6): eine Arbeitszahl unter 2 trägt ihren Satz', () => {
    expect(REGELN_OFFEN['§2.2.1/W-6']).toBeUndefined()
    // dietmars Juli: 309 kWh Wärme ÷ 337 kWh Strom = 0,92 — praktisch genau
    // das, was reiner Heizstab-Betrieb ergeben MUSS. Die Zahl ist richtig
    // (Fall H-B), es fehlte der Satz daneben.
    //
    // ⭐ **Zahl und Satz kommen jetzt BEIDE aus dem Backend.** Der Client
    // rechnet die JAZ nicht mehr selbst (W-3) und kennt die Schwelle nicht —
    // er zeigt, was der Layer schickt. Deshalb setzt die Probe hier
    // `wp_jaz`/`wp_jaz_hinweis` wie die Response es tut; **die Schwelle selbst
    // ist im Backend geprüft** (`test_soll_waerme_klima_achse2_abgrenzung.py`).
    // Eine Probe, die hier weiter aus Wärme ÷ Strom rechnete, würde eine
    // Client-Formel prüfen, die es nicht mehr gibt.
    rendereWpBlock({
      wp_strom_kwh: 337, wp_waerme_kwh: 309, wp_jaz: 0.92,
      wp_jaz_hinweis: 'Eine Arbeitszahl nahe 1 entsteht, wenn ein großer Teil der '
        + 'Wärme direkt elektrisch erzeugt wurde (Heizstab, Zusatz- oder '
        + 'Notheizung). Die Zahl beschreibt die Anlage in diesem Zeitraum, sie '
        + 'ist kein Fehler.',
    })

    expect(screen.getByText('0,92')).toBeTruthy()
    expect(screen.getByText(/Heizstab/)).toBeTruthy()
  })

  it('ERFÜLLT: eine unauffällige Arbeitszahl braucht keinen Satz', () => {
    // Gegenprobe zur Schwelle: Der Hinweis aus W-6 darf nicht überall stehen,
    // sonst erklärt er nichts mehr. SOLL nennt „unter etwa 2".
    rendereWpBlock({ wp_strom_kwh: 500, wp_waerme_kwh: 2000, wp_jaz: 4.0 })

    expect(screen.getByText('4,00')).toBeTruthy()
    expect(screen.queryByText(/Heizstab|Elektroheizung/i)).toBeNull()
  })

  it('ERFÜLLT (S3): fehlt die Arbeitszahl, steht der Grund daneben', () => {
    // Der Unterschied zwischen „—" und einer Auskunft. Der Grund entsteht dort,
    // wo die Sperre entscheidet — im Layer —, nicht als Client-Vermutung.
    rendereWpBlock({
      wp_strom_kwh: 337, wp_waerme_kwh: null, wp_jaz: null,
      wp_jaz_grund: 'kein Wärmemengenzähler zugeordnet',
    })

    // Sichtbar unter der Zahl, nicht im Hover-Tooltip: S3 verlangt eine
    // Auskunft, und ein Tooltip ist auf dem Telefon keine.
    expect(screen.getByText('kein Wärmemengenzähler zugeordnet')).toBeTruthy()
  })
})

// ══ III-3 · OFFEN — S2: zwei Größen teilen sich einen Balkenplatz ═══════════

describe('Achse III-3 — ein Balken sagt, was er zeigt', () => {
  it('ERFÜLLT (S2/W-8): die Wärme-Aufteilung nennt ihre Größe in der Anzeige', () => {
    expect(REGELN_OFFEN['S2/W-8']).toBeUndefined()
    // dietmars Juli-Bild: Balken „Heizung" / „Warmwasser" — das sind WÄRME-kWh.
    rendereWpBlock({
      wp_strom_kwh: 337, wp_waerme_kwh: 309,
      wp_heizung_kwh: 0, wp_warmwasser_kwh: 309,
    })

    expect(screen.getByText('Heizung')).toBeTruthy()
    expect(screen.getByText('Warmwasser')).toBeTruthy()
    // S2: „Wechselt der Inhalt je nach Datenlage, wechselt auch die
    // Beschriftung." Der Element-Titel existierte schon — er ging bis
    // 26.08.2026 nur an den Park-Chip und war in der Anzeige unsichtbar.
    expect(screen.getByText('Wärme-Aufteilung')).toBeTruthy()
  })

  it('ERFÜLLT (S2/W-8): die Strom-Aufteilung nennt ihre Größe erst recht', () => {
    expect(REGELN_OFFEN['S2/W-8']).toBeUndefined()
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
    // Der Titel nennt die Größe: „Aufteilung Heizen/Kühlen" allein sagte
    // nicht, dass hier STROM steht — direkt darüber kann die Wärme-Aufteilung
    // liegen, mit denselben Balken und anderer Einheit.
    expect(screen.getByText('Strom-Aufteilung Heizen/Kühlen')).toBeTruthy()
  })

  it('ERFÜLLT (S2/W-8): derselbe Platz sagt in zwei Monaten, welche Größe er zeigt', () => {
    expect(REGELN_OFFEN['S2/W-8']).toBeUndefined()
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
    expect(cAug.textContent).not.toContain('Warmwasser')
    // ⭐ **Das ist die eigentliche Auflösung von dietmars Beschwerde.** Nicht
    // dass Warmwasser verschwindet — das ist richtig, es gibt im August keine
    // gepflegte Wärme-Aufteilung —, sondern dass der Platz jetzt sagt, welche
    // Größe er gerade zeigt. Das Verschwinden ist damit erklärt statt rätselhaft.
    expect(cJuli.textContent).toContain('Wärme-Aufteilung')
    expect(cAug.textContent).toContain('Strom-Aufteilung Heizen/Kühlen')
    expect(cJuli.textContent).not.toContain('Strom-Aufteilung')
  })
})
