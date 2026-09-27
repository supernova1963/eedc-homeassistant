/**
 * **N-371 — die Option „Fremdanteil auf den Zählern" nennt die Klasse, nicht ein Gerät.**
 *
 * Es ist die **einzige** Angabe, mit der ein Anwender eedc sagen kann, dass sein
 * WP-Stromzähler mehr misst als die Wärmepumpe — und je einzelnem Gerät die
 * einzige Lage, die die Arbeitszahl-Sperre überhaupt auslöst. Bis zum
 * 13.09.2026 hieß sie „Heizstab-Strom liegt mit auf dem Stromzähler". Wer eine
 * **Klimaanlage** auf demselben Zähler hat (dietmar1968, T89667 #290), suchte
 * unter „Heizstab", fand nichts — und bekam weiter eine Arbeitszahl, die zwei
 * Geräte mischt.
 *
 * ⚠ **Gelesen wird das gerenderte `<option>`, nicht die Konstante.** Ein Test,
 * der `ABGRENZUNG_OPTIONEN` importiert, prüft, dass ein Text mit sich selbst
 * übereinstimmt; ob er beim Anwender ankommt, sagt er nicht. Die Konstante ist
 * modul-privat, und das soll sie bleiben.
 *
 * ⛔ **Der Heizstab muss als Beispiel drin bleiben** — nicht aus Nostalgie:
 * ``test_n349_beide_lagen_nennen_den_heizstab_und_das_ist_die_aussage``
 * (Backend) hält fest, dass **beide** Lagen ihn nennen, weil nicht das Gerät
 * über den Fall entscheidet, sondern wo die Zähler sitzen. Die Beschreibung
 * unter dem Feld nennt ihn nicht — das Label ist die einzige Stelle.
 */
import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

import { WaermepumpeFelder } from './WaermepumpeFelder'

const noop = () => {}

/** Rendert das WP-Formular und gibt die Auswahl „Fremdanteil auf den Zählern" zurück. */
function fremdanteilAuswahl(params: Record<string, unknown> = {}) {
  render(
    <WaermepumpeFelder
      paramData={{ wp_art: 'luft_wasser', ...params }}
      onInputChange={noop}
      setParam={noop}
      zeige={() => undefined}
      markTouched={noop}
      setFeldRef={() => () => {}}
    />,
  )
  return screen.getByLabelText(/Fremdanteil auf den Zählern/) as HTMLSelectElement
}

describe('WaermepumpeFelder — Fremdanteil auf den Zählern (N-371)', () => {
  it('nennt bei `fremdstrom` einen weiteren Verbraucher, nicht nur den Heizstab', () => {
    const auswahl = fremdanteilAuswahl()
    const option = Array.from(auswahl.options).find((o) => o.value === 'fremdstrom')

    expect(option).toBeTruthy()
    expect(option!.textContent).toBe(
      'Ein weiterer Verbraucher liegt mit auf dem Stromzähler (z. B. Heizstab)',
    )
  })

  it('führt den Heizstab weiter als Beispiel — beide Lagen nennen ihn (N-349)', () => {
    const auswahl = fremdanteilAuswahl()
    const beschriftungen = Array.from(auswahl.options).map((o) => o.textContent ?? '')

    // Die `fremdstrom`-Zeile darf das Beispiel nicht verlieren; sonst liest
    // sich die Liste wieder als Geräte-Aufzählung.
    expect(beschriftungen.filter((t) => t.includes('Heizstab'))).toHaveLength(1)
  })

  it('behält den gespeicherten Wert `fremdstrom` — eine Beschriftung braucht keine Migration', () => {
    const auswahl = fremdanteilAuswahl({ abgrenzung: 'fremdstrom' })

    expect(auswahl.value).toBe('fremdstrom')
    expect(Array.from(auswahl.options).map((o) => o.value)).toEqual([
      '', 'fremdstrom', 'fremdwaerme',
    ])
  })

  it('lässt die Beschreibung unter dem Feld unverändert bei der Zählerlage', () => {
    // Sie war schon vorher allgemein formuliert (Fundtext N-371) und trägt die
    // eigentliche Aussage: nicht das Gerät entscheidet, sondern der Zähler.
    render(
      <WaermepumpeFelder
        paramData={{ wp_art: 'luft_wasser', abgrenzung: 'fremdstrom' }}
        onInputChange={noop}
        setParam={noop}
        zeige={() => undefined}
        markTouched={noop}
        setFeldRef={() => () => {}}
      />,
    )

    expect(
      screen.getByText(/Seine Wärme läuft NICHT über den Wärmemengenzähler/),
    ).toBeTruthy()
  })
})

describe('WaermepumpeFelder — „PV-Anteil (%)" sagt, was er tut (N-459 / SOLL S1b)', () => {
  /**
   * ⛔ **Bis zum 13.09.2026 stand am Feld nur „Anteil des WP-Stroms aus PV".**
   * Das war zwar richtig, aber unvollständig — und die Lücke war teuer: Der
   * Wert ging in die ROI-Zeile ein und **senkte dort die Stromkosten der
   * Wärmepumpe**, obwohl derselbe PV-Strom auf der PV-Seite bereits als
   * Eigenverbrauch gutgeschrieben ist. Seit S1b liest keine Geldformel das
   * Feld mehr; es beantwortet eine **Mengenfrage**. Der Hinweis sagt das jetzt.
   *
   * ⚠ Gelesen wird der gerenderte Hinweistext, nicht eine Konstante — sonst
   * prüfte die Probe einen Text gegen sich selbst.
   */
  function pvAnteilHinweis() {
    render(
      <WaermepumpeFelder
        paramData={{ wp_art: 'luft_wasser' }}
        onInputChange={noop}
        setParam={noop}
        zeige={() => undefined}
        markTouched={noop}
        setFeldRef={() => () => {}}
      />,
    )
    // ⚠ Das Feld steht in der Sektion „Vergleich mit alter Heizung (ROI)",
    // und die ist `variant="erweitert"` — eingeklappt, und ihr Inhalt ist
    // dann gar nicht im DOM. Ohne diesen Klick fände die Probe nichts und
    // wäre grün zu bekommen, indem man den Text falsch schreibt.
    fireEvent.click(screen.getByRole('button', { name: /Vergleich mit alter Heizung/ }))
    return screen.getByText(/Anteil des WP-Stroms aus PV/)
  }

  it('sagt, dass das Feld die Stromkosten der Wärmepumpe NICHT senkt', () => {
    // N-572 (27.09.2026): der Hinweis trägt seither zwei Sätze mehr — was ein
    // leeres Feld bedeutet. Die Aussage dieser Probe steht unverändert vorn.
    expect(pvAnteilHinweis().textContent).toBe(
      'Anteil des WP-Stroms aus PV — dient der Zuordnung des Eigenverbrauchs, '
      + 'senkt die Stromkosten der Wärmepumpe nicht. Nie eingetragen: eedc rechnet '
      + 'mit 30 %. Leerst du einen eingetragenen Wert, zählt diese Wärmepumpe nicht '
      + 'mehr zum Prognose-Mittel der PV-Anteile.',
    )
  })

  it('nennt weiterhin, wofür der Wert gebraucht wird — sonst wirkt das Feld überflüssig', () => {
    // Eine reine Verneinung („senkt nichts") ließe den Anwender ratlos zurück,
    // warum er das Feld dann pflegen soll. Der Zweck steht davor.
    expect(pvAnteilHinweis().textContent).toMatch(/Zuordnung des Eigenverbrauchs/)
  })
})

/**
 * **WK-15c — das Feld „Heizwärmebedarf" an einem Gerät ohne Heiz-Achse.**
 *
 * Handbuch WAERME_KLIMA §6/F sagt der Brauchwasser-Wärmepumpe zu: *„die
 * Heiz-Achse wird weder angeboten noch erwartet."* Der Daten-Checker fragt seit
 * WK-15b nicht mehr danach — das Formular bot das Feld weiter an und belegte es
 * mit 12.000 kWh vor.
 *
 * ⚠ **Die Klimaanlage behält es** (N-88/F2b): Sie hat eine Heiz-Achse, viele
 * heizen mit ihr, und ihre Ersparnis hängt an genau dieser Zahl.
 */
describe('WaermepumpeFelder — Heizwärmebedarf nur mit Heiz-Achse (WK-15c)', () => {
  function felder(wpArt: string) {
    render(
      <WaermepumpeFelder
        paramData={{ wp_art: wpArt }}
        onInputChange={noop}
        setParam={noop}
        zeige={() => undefined}
        markTouched={noop}
        setFeldRef={() => () => {}}
      />,
    )
    return {
      heiz: screen.queryByLabelText(/Heizwärmebedarf/),
      ww: screen.queryByLabelText(/Warmwasserbedarf/),
    }
  }

  it('bietet der Brauchwasser-Wärmepumpe keinen Heizwärmebedarf an', () => {
    const { heiz, ww } = felder('brauchwasser')
    expect(heiz).toBeNull()
    expect(ww).not.toBeNull()
  })

  it('behält beide Felder an der Klimaanlage (N-88/F2b) und an der Luft-Wasser-WP', () => {
    for (const art of ['luft_luft', 'luft_wasser']) {
      const { heiz, ww } = felder(art)
      expect(heiz, art).not.toBeNull()
      expect(ww, art).not.toBeNull()
    }
  })
})
