/**
 * Der Betriebsmodus-Klartext im Energiefluss darf den Gerätenamen nicht überdecken.
 *
 * **Anlass: MartyBr, Forum simon42 T89667 #230**, am Tag der v4.0.30-Auslieferung.
 * Sein Bild zeigt „Unbestimmt" quer über „Vitocal 33…" — beide Texte lagen vier
 * Pixel auseinander, bei neun Pixel Schriftgröße.
 *
 * ⭐ **Die Ursache war eine Frage, die an zwei Stellen beantwortet wurde.**
 * Der Modus-Text (#398 Stufe 2) hat sich die **Position** der SoC-Zeile geliehen
 * (`kwFontSize + 2`) — richtig, ein Gerät hat nie beides. Die **Verschiebung des
 * Namens** darunter stand aber in einem Ternär, das nur `hasSoc` kannte. Wer die
 * eine Stelle ändert und die andere übersieht, baut genau diese Überlagerung.
 * Seit dem Fix steht die Frage einmal (`zweiteZeile`).
 *
 * ⚠ **Geprüft wird die Geometrie, nicht das Aussehen.** Kein Test misst Pixel auf
 * einem Bildschirm; was er messen kann, ist, dass zwei Texte verschiedene
 * `y`-Werte tragen und der Abstand zur Schriftgröße passt. Für alles Weitere gilt
 * unverändert: bei Layout-Punkten entscheidet der Screenshot.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import EnergieFluss from './EnergieFluss'
import { ThemeProvider } from '../../context/ThemeContext'
import { stubMatchMedia } from '../../test/render'
import type { LiveKomponente, LiveGauge } from '../../api/liveDashboard'

beforeEach(() => {
  // Der Energiefluss zieht seine Achsenfarben aus dem Theme; der Provider
  // fragt die Systemeinstellung ab, und jsdom kennt `matchMedia` nicht.
  stubMatchMedia()
})

const wp = (over: Partial<LiveKomponente> = {}): LiveKomponente => ({
  key: 'waermepumpe_7',
  label: 'Vitocal 333-G',
  icon: 'flame',
  erzeugung_kw: null,
  verbrauch_kw: 0.9,
  ...over,
})

const speicher = (over: Partial<LiveKomponente> = {}): LiveKomponente => ({
  key: 'batterie_3',
  label: 'Hausspeicher',
  icon: 'battery',
  erzeugung_kw: 0.4,
  verbrauch_kw: null,
  ...over,
})

function zeichne(komponenten: LiveKomponente[], gauges: LiveGauge[] = []) {
  return render(
    <ThemeProvider>
      <EnergieFluss
        komponenten={komponenten}
        summeErzeugung={3}
        summeVerbrauch={1.3}
        summePv={3}
        gauges={gauges}
      />
    </ThemeProvider>,
  )
}

/** `y` des SVG-Textknotens mit genau diesem Inhalt. */
function textY(container: HTMLElement, inhalt: string): number {
  const treffer = [...container.querySelectorAll('text')].filter(
    t => t.textContent?.trim() === inhalt,
  )
  expect(treffer, `kein <text> mit „${inhalt}"`).toHaveLength(1)
  return Number(treffer[0].getAttribute('y'))
}

describe('EnergieFluss — Betriebsmodus und Gerätename', () => {
  it('legt den Modus-Klartext nicht auf den Gerätenamen (MartyBr #230)', () => {
    const { container } = zeichne([wp({ betriebsmodus: 'heizen', betriebsmodus_label: 'Heizen' })])

    const yModus = textY(container, 'Heizen')
    const yName = textY(container, 'Vitocal 333-G')

    expect(yName).toBeGreaterThan(yModus)
    // Der Name muss um mindestens eine Zeilenhöhe tiefer stehen. Vor dem Fix
    // lagen 4 px dazwischen — dieser Wert ist die Grenze, unterhalb derer sich
    // zwei Texte dieser Größe berühren.
    expect(yName - yModus).toBeGreaterThanOrEqual(8)
  })

  it('lässt den Namen an seinem Platz, wenn es keine zweite Zeile gibt', () => {
    const ohne = zeichne([wp()])
    const mit = zeichne([wp({ betriebsmodus: 'kuehlen', betriebsmodus_label: 'Kühlen' })])

    const yOhne = textY(ohne.container, 'Vitocal 333-G')
    const yMit = textY(mit.container, 'Vitocal 333-G')

    // Die Gegenprobe zum Fix: er verschiebt den Namen NUR dort, wo eine zweite
    // Zeile ihn verdrängt — nicht generell.
    expect(yMit).toBeGreaterThan(yOhne)
  })

  it('behandelt den SoC unverändert — der Fix ändert die eingeführte Seite nicht', () => {
    const { container } = zeichne(
      [speicher()],
      [{ key: 'soc_3', label: 'Hausspeicher', wert: 62, min_wert: 0, max_wert: 100, einheit: '%' }],
    )

    const ySoc = textY(container, '62 %')
    const yName = textY(container, 'Hausspeicher')

    expect(yName - ySoc).toBeGreaterThanOrEqual(8)
  })

  it('zeigt gar keinen Modus-Text, wenn das Backend keinen Klartext liefert', () => {
    // Das ist MartyBrs eigentlicher Fall nach dem Backend-Fix: `unbestimmt`
    // kommt ohne Label an, die Kachel trägt nur Leistung und Name.
    const { container } = zeichne([wp({ betriebsmodus: 'unbestimmt', betriebsmodus_label: null })])

    expect(
      [...container.querySelectorAll('text')].some(t => /unbestimmt/i.test(t.textContent ?? '')),
    ).toBe(false)
  })
})
