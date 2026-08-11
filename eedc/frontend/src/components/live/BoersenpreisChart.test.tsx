/**
 * Börsenpreis-Chart (#335) — Achsenaufbau, Farbstufen, Günstig-Flächen.
 *
 * ⚠ **Was diese Datei NICHT prüft:** das gezeichnete Bild. In jsdom hat der
 * Recharts-`ResponsiveContainer` 0×0 und rendert weder Linien noch Flächen
 * ([[reference_recharts_bars_jsdom]]). Geprüft wird deshalb die Rechenschicht,
 * die davor liegt — und genau dort sitzen die Entscheidungen, die falsch sein
 * können: welche Stunde an welcher Position steht, wo die Farbkanten liegen und
 * ob eine Lücke Lücke bleibt.
 */

import { describe, it, expect } from 'vitest'
import type { BoersenpreisTag } from '../../api/liveDashboard'
import { CHART_FLAECHE, PREISSTUFEN_FARBEN } from '../../lib'
import {
  baueAchse, farbStops, guenstigeBereiche, zeitumstellungHinweis, RangZiffer,
} from './BoersenpreisChart'

// Die Stufenfarben hängen am Modus (Kontrast-Messung, s. `PREISSTUFEN_FARBEN`).
// Die Proben fahren ausdrücklich EINE Palette — sonst prüften sie mit, welcher
// Modus zufällig voreingestellt ist.
const HELL = PREISSTUFEN_FARBEN.light

function stunde(h: number, preis: number, guenstig = false, rang = 99) {
  // `abstand_cent` (N-173) ist hier bewusst null: der Chart färbt nach
  // `unter_schwelle` und liest die Größe nicht — was diese Proben auch prüfen,
  // indem sie ohne sie auskommen. Die Kennzahl darauf prüft der Block-Test.
  return { stunde: h, preis_cent: preis, rang, unter_schwelle: guenstig, abstand_cent: null }
}

/** Ein Tag mit 24 Stunden; die Stunden in `guenstig` liegen unter der Schwelle. */
function tag(datum: string, preise: number[], guenstig: number[] = []): BoersenpreisTag {
  return {
    datum,
    stunden: preise.map((p, h) => stunde(h, p, guenstig.includes(h))),
    schwelle_cent: 9,
    optimierter_durchschnitt_cent: 10,
  }
}

const FLACH = Array.from({ length: 24 }, (_, h) => 10 + h * 0.1)

describe('baueAchse', () => {
  it('legt zwei Tage hintereinander auf eine durchgehende Achse', () => {
    const punkte = baueAchse([tag('2026-08-06', FLACH), tag('2026-08-07', FLACH)])

    // 2 × 24 Stunden + der Schlusspunkt, der die letzte Stufe bis Mitternacht zieht.
    expect(punkte).toHaveLength(49)
    expect(punkte[0].pos).toBe(0)
    expect(punkte[24].pos).toBe(24)
    expect(punkte[48].pos).toBe(48)
    // Jeder Tag hat seine eigene Serie — sonst ließe sich nicht je Tag mit
    // eigener Schwelle einfärben.
    expect(punkte[5].preis_0).not.toBeNull()
    expect(punkte[5].preis_1).toBeNull()
    expect(punkte[30].preis_0).toBeNull()
    expect(punkte[30].preis_1).not.toBeNull()
  })

  it('schließt die Naht zwischen den Tagen, damit die Linie nicht abreißt', () => {
    const punkte = baueAchse([tag('2026-08-06', FLACH), tag('2026-08-07', FLACH)])

    const naht = punkte.find((p) => p.pos === 24)!
    // Der letzte Wert von Tag 0 reicht bis an die erste Position von Tag 1 —
    // ohne ihn klaffte im Bild genau eine Stunde Lücke an der Tagesgrenze.
    expect(naht.preis_0).toBe(FLACH[23])
    expect(naht.preis_1).toBe(FLACH[0])
  })

  it('zieht die letzte Stufe bis Mitternacht aus', () => {
    const punkte = baueAchse([tag('2026-08-06', FLACH)])

    const schluss = punkte[punkte.length - 1]
    expect(schluss.pos).toBe(24)
    expect(schluss.preis_0).toBe(FLACH[23])
    // Der Schlusspunkt ist keine eigene Stunde und darf deshalb auch keine
    // Günstig-Fläche auslösen.
    expect(schluss.guenstig).toBeNull()
  })

  it('lässt die fehlende Stunde der Zeitumstellung als Lücke stehen', () => {
    // Ende März: die Stunde 2 gibt es nicht (F-6). Sie darf NICHT durch einen
    // Nachbarwert ersetzt werden — das wäre ein Preis für eine Stunde, die es
    // nie gab.
    const kurz: BoersenpreisTag = {
      datum: '2027-03-28',
      stunden: FLACH.map((p, h) => stunde(h, p)).filter((s) => s.stunde !== 2),
      schwelle_cent: 9,
      optimierter_durchschnitt_cent: 10,
    }
    const punkte = baueAchse([kurz])

    expect(punkte.find((p) => p.stunde === 2)!.preis_0).toBeNull()
    // Und die Positionen danach verrutschen nicht: Stunde 3 liegt an Position 3.
    expect(punkte.find((p) => p.pos === 3)!.stunde).toBe(3)
  })

  it('hält die Positionen stabil, auch wenn heute kurz war', () => {
    // Sonst läge „morgen 14 Uhr" an Position 37 statt 38 — die Zeitachse eines
    // Umstellungstages würde den Folgetag mitverschieben.
    const kurz: BoersenpreisTag = {
      datum: '2027-03-28',
      stunden: FLACH.map((p, h) => stunde(h, p)).filter((s) => s.stunde !== 2),
      schwelle_cent: 9, optimierter_durchschnitt_cent: 10,
    }
    const punkte = baueAchse([kurz, tag('2027-03-29', FLACH)])

    const morgen14 = punkte.find((p) => p.pos === 38)!
    expect(morgen14.stunde).toBe(14)
    expect(morgen14.datum).toBe('2027-03-29')
  })

  it('kommt mit einem einzigen Tag aus (vormittags gibt es morgen noch nicht)', () => {
    const punkte = baueAchse([tag('2026-08-06', FLACH)])
    expect(punkte).toHaveLength(25)
    expect(punkte.every((p) => p.preis_1 === null)).toBe(true)
  })

  it('gibt bei gar keinen Tagen eine leere Achse', () => {
    expect(baueAchse([])).toEqual([])
  })
})

describe('farbStops', () => {
  it('setzt harte Kanten an Schwelle und Durchschnitt', () => {
    // Spanne 5…15, Schwelle 9, Ø 10.
    const stops = farbStops([5, 8, 9, 10, 12, 15], 9, 10, HELL)

    expect(stops[0].farbe).toBe(HELL.teuer)      // oben = teuerste Stunde
    expect(stops[stops.length - 1].farbe).toBe(HELL.guenstig)
    // Jede Grenze erzeugt ZWEI Stops auf demselben Offset — ein weicher Verlauf
    // würde eine Zwischenstufe behaupten, die es in der Bewertung nicht gibt.
    const doppelte = stops.filter((s, i) => i > 0 && stops[i - 1].offset === s.offset)
    expect(doppelte).toHaveLength(2)
  })

  it('legt die Kante dorthin, wo die Grenze in der Kurve liegt', () => {
    // Spanne 0…10, Ø 10 (= Maximum, also keine eigene Kante), Schwelle 5 → Mitte.
    const stops = farbStops([0, 5, 10], 5, 10, HELL)
    const kante = stops.find((s, i) => i > 0 && stops[i - 1].offset === s.offset)!
    // offset 0 = teuerste Stunde (10), offset 1 = billigste (0) ⇒ 5 liegt bei 0,5.
    expect(kante.offset).toBeCloseTo(0.5, 6)
  })

  it('kippt bei negativen Preisen nicht die Reihenfolge', () => {
    // Day-Ahead wird regelmäßig negativ (am 06.08.2026 gemessen: −0,14 ct).
    // Unten muss trotzdem die billigste Stunde stehen.
    const stops = farbStops([-2, 0, 4, 12], 1, 5, HELL)
    expect(stops[0].farbe).toBe(HELL.teuer)
    expect(stops[stops.length - 1].farbe).toBe(HELL.guenstig)
    expect(stops.every((s) => s.offset >= 0 && s.offset <= 1)).toBe(true)
  })

  it('färbt eine flache Kurve einfarbig statt durch Null zu teilen', () => {
    const stops = farbStops([7, 7, 7], 9, 10, HELL)
    expect(stops).toHaveLength(2)
    expect(stops[0].farbe).toBe(HELL.guenstig)
    expect(stops.every((s) => Number.isFinite(s.offset))).toBe(true)
  })

  it('kommt ohne Schwelle aus (zu wenige Preise für einen Ø)', () => {
    const stops = farbStops([5, 10], null, null, HELL)
    expect(stops.every((s) => s.farbe === HELL.normal)).toBe(true)
  })

  it('liefert ohne Werte gar keine Stops statt NaN-Offsets', () => {
    expect(farbStops([], 9, 10, HELL)).toEqual([])
  })
})

describe('guenstigeBereiche', () => {
  it('fasst zusammenhängende günstige Stunden zu einem Bereich', () => {
    const punkte = baueAchse([tag('2026-08-06', FLACH, [2, 3, 4, 14])])
    const bereiche = guenstigeBereiche(punkte)

    expect(bereiche).toEqual([{ von: 2, bis: 5 }, { von: 14, bis: 15 }])
  })

  it('folgt der ungekappten Markierung, nicht dem Rang (N-103)', () => {
    // Acht Stunden unter der Schwelle, aber nur fünf können einen Rang tragen.
    // Ein Chart, der dem Rang folgte, ließe drei günstige Stunden ungefärbt.
    const guenstig = [0, 1, 2, 3, 4, 5, 6, 7]
    const stunden = FLACH.map((p, h) =>
      stunde(h, p, guenstig.includes(h), guenstig.indexOf(h) >= 0 && guenstig.indexOf(h) < 5
        ? guenstig.indexOf(h) + 1 : 99),
    )
    const punkte = baueAchse([{
      datum: '2026-08-06', stunden, schwelle_cent: 9, optimierter_durchschnitt_cent: 10,
    }])

    const bereiche = guenstigeBereiche(punkte)
    expect(bereiche).toEqual([{ von: 0, bis: 8 }])
    const mitRang = stunden.filter((s) => s.rang !== 99)
    expect(mitRang).toHaveLength(5)
  })

  it('meldet keine Bereiche, wenn keine Stunde günstig ist', () => {
    expect(guenstigeBereiche(baueAchse([tag('2026-08-06', FLACH)]))).toEqual([])
  })
})

describe('zeitumstellungHinweis', () => {
  it('schweigt an einem gewöhnlichen Tag', () => {
    expect(zeitumstellungHinweis([tag('2026-08-06', FLACH)])).toBeNull()
  })

  it('benennt den kurzen Tag, statt die Lücke zu verschweigen', () => {
    const kurz: BoersenpreisTag = {
      datum: '2027-03-28',
      stunden: FLACH.map((p, h) => stunde(h, p)).filter((s) => s.stunde !== 2),
      schwelle_cent: 9, optimierter_durchschnitt_cent: 10,
    }
    const hinweis = zeitumstellungHinweis([kurz])
    expect(hinweis).toContain('23')
    expect(hinweis).toContain('28.03.')
  })
})

// ── Die Stufenfarben müssen sichtbar UND voneinander unterscheidbar sein ────
//
// Zwei verschiedene Prüfungen, und genau das war der Blindfleck: gemessen wurde
// beim Bau nur die erste.
//
// (1) Sichtbarkeit — Kontrast zum Hintergrund. Die erste Fassung nahm je Stufe
//     EINE feste Farbe und fiel in je einem Modus unter die 3:1-Schwelle für
//     grafische Objekte (WCAG 1.4.11): Grün-500 auf Weiß nur 2,28:1, Purple-700
//     auf dunklem Grund 2,10:1 — dort war die teure Stufe praktisch unsichtbar.
// (2) Unterscheidbarkeit — Abstand der Stufen ZUEINANDER, in Helligkeit und
//     Farbton. Beide Randstufen können jede für sich gut sichtbar sein und
//     trotzdem miteinander verschmelzen; genau so kam die Meldung von
//     Radiocarbonat (T89667 #110, 2026-08-07): zwei Legendenpunkte von 8×12 px,
//     beide kontrastreich, beide Lila, für ihn nicht auseinanderzuhalten.
//
// `check:design` deckt keine der beiden ab — er prüft die Herkunft aus der
// Farb-SoT, nicht das Ergebnis. Diese Proben halten die Messung fest.

/** Relative Leuchtdichte nach WCAG 2.1 (sRGB). */
function leuchtdichte(hex: string): number {
  const kanal = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4))
  return 0.2126 * kanal[0] + 0.7152 * kanal[1] + 0.0722 * kanal[2]
}

function kontrast(a: string, b: string): number {
  const [hoch, tief] = [leuchtdichte(a), leuchtdichte(b)].sort((x, y) => y - x)
  return (hoch + 0.05) / (tief + 0.05)
}

/** Farbton (HSL-Hue) in Grad, 0–360. */
function farbton(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
  const max = Math.max(r, g, b)
  const spanne = max - Math.min(r, g, b)
  if (spanne === 0) return 0
  const h = max === r ? ((g - b) / spanne) % 6
    : max === g ? (b - r) / spanne + 2
      : (r - g) / spanne + 4
  return ((h * 60) % 360 + 360) % 360
}

/** Kürzester Abstand zweier Farbtöne auf dem Farbkreis (0–180 Grad). */
function farbtonAbstand(a: string, b: string): number {
  const d = Math.abs(farbton(a) - farbton(b))
  return Math.min(d, 360 - d)
}

describe('PREISSTUFEN_FARBEN', () => {
  it.each(['light', 'dark'] as const)('hebt sich in %s vom Hintergrund ab', (modus) => {
    const stufen = PREISSTUFEN_FARBEN[modus]
    for (const [name, farbe] of Object.entries(stufen)) {
      expect(
        kontrast(farbe, CHART_FLAECHE[modus]),
        `${name} in ${modus} (${farbe})`,
      ).toBeGreaterThanOrEqual(3)
    }
  })

  it.each(['light', 'dark'] as const)('trennt normal und teuer in %s hörbar', (modus) => {
    // ⚠ Diese Probe EXISTIERTE, als der Fehler gemeldet wurde — sie stand nur zu
    // weich. Ihre Schwelle war 1,4; die beanstandeten Lila-Töne erreichten 1,76
    // (hell) und 1,61 (dunkel) und liefen damit grün durch (T89667 #110,
    // Radiocarbonat). Die Schwelle liegt jetzt ÜBER dem gemeldeten Ist-Wert —
    // eine Schwelle unterhalb dessen, was ein Melder als ununterscheidbar
    // beschreibt, prüft nichts.
    const { normal, teuer } = PREISSTUFEN_FARBEN[modus]
    expect(kontrast(normal, teuer)).toBeGreaterThanOrEqual(2)
  })

  it.each(['light', 'dark'] as const)('trennt normal und teuer in %s auch im Farbton', (modus) => {
    // Die zweite Hälfte der Prüfung, die beim Bau fehlte: Helligkeit ALLEIN kann
    // die beiden nicht trennen, solange die Mitte die Rollenfarbe bleibt — 3:1
    // zur Mitte ist dann rechnerisch unerreichbar, weil eine so viel hellere
    // Farbe auf dem Hintergrund steht. Also muss der Farbton tragen.
    const { normal, teuer } = PREISSTUFEN_FARBEN[modus]
    expect(farbtonAbstand(normal, teuer)).toBeGreaterThanOrEqual(60)
  })

  it('lässt die Mitte in beiden Modi die Rollenfarbe des Strompreises sein', () => {
    // Wandert die Mitte mit, ist es keine Abstufung einer Rolle mehr, sondern
    // eine zweite Palette.
    expect(PREISSTUFEN_FARBEN.light.normal).toBe(PREISSTUFEN_FARBEN.dark.normal)
  })
})

// ── Rang 1–5 im Chart (Rainer-PN 11.08., Gernots Entscheid) ─────────────────

describe('Rang-Markierung', () => {
  it('trägt den Rang des Backends an die Achsenposition', () => {
    const t = tag('2026-08-06', FLACH, [0, 1, 2])
    t.stunden[0].rang = 1
    t.stunden[1].rang = 2
    t.stunden[5].rang = 99
    const punkte = baueAchse([t])

    expect(punkte[0].rang).toBe(1)
    expect(punkte[1].rang).toBe(2)
    expect(punkte[5].rang).toBe(99)
  })

  it('gibt dem Schlusspunkt keinen Rang', () => {
    // Er ist keine eigene Stunde, sondern das Ende der vorigen — sonst stünde
    // dieselbe Ziffer zweimal im Bild (gleiche Begründung wie bei `guenstig`).
    const punkte = baueAchse([tag('2026-08-06', FLACH)])
    expect(punkte[punkte.length - 1].rang).toBeNull()
  })

  it('zeichnet nur die Ränge 1–5, nicht den Rest', () => {
    const gezeichnet = (rang: number | null) =>
      RangZiffer({
        cx: 10, cy: 20, farbe: HELL.guenstig,
        payload: { pos: 0, label: 'Do 03', preis_0: 5, preis_1: null, stunde: 3, datum: '2026-08-06', guenstig: true, rang },
      })

    expect(gezeichnet(1)).not.toBeNull()
    expect(gezeichnet(5)).not.toBeNull()
    // 99 = teuer/Rest. Ohne diese Grenze stünde an JEDER Stunde ein Punkt.
    expect(gezeichnet(99)).toBeNull()
    expect(gezeichnet(null)).toBeNull()
  })

  it('zeichnet nichts ohne Koordinaten', () => {
    // Recharts ruft den Dot auch für Lücken auf (Zeitumstellung, F-6).
    expect(RangZiffer({ farbe: HELL.guenstig, payload: { pos: 0, label: 'Do 02', preis_0: null, preis_1: null, stunde: 2, datum: '2027-03-28', guenstig: null, rang: 1 } })).toBeNull()
  })

  it('lässt die Günstig-Menge unangetastet — Rang ist eine ZWEITE Aussage', () => {
    // Die Gegenprobe zu dem, was NICHT gebaut wurde: Rainers Wunsch „nur fünf
    // günstige Stunden" hätte die seit v4.0.10 ungekappte Zählung gedeckelt, die
    // in Automationen als Divisor dient (N-103). Acht Stunden unter der Schwelle
    // bleiben acht — auch wenn nur fünf eine Ziffer tragen.
    const t = tag('2026-08-06', FLACH, [0, 1, 2, 3, 4, 5, 6, 7])
    t.stunden.forEach((s, h) => { s.rang = h < 5 ? h + 1 : 99 })
    const punkte = baueAchse([t])

    expect(punkte.filter((p) => p.guenstig).length).toBe(8)
    expect(punkte.filter((p) => p.rang != null && p.rang <= 5).length).toBe(5)
    expect(guenstigeBereiche(punkte)).toEqual([{ von: 0, bis: 8 }])
  })
})
