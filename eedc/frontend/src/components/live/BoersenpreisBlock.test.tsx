/**
 * Börsenpreis-Block (#335) — Kennzahlen und was der Block sagt, wenn Daten fehlen.
 *
 * Die drei Kennzahlen sind dieselben Größen, die die HA-Sensoren melden. Wichtig
 * ist hier vor allem die Günstig-Zählung: Sie ist **ungekappt** (N-103) und darf
 * nicht wieder auf die fünf Ränge zurückfallen, aus denen sie bis v4.0 kam.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { BoersenpreisResponse, BoersenpreisTag } from '../../api/liveDashboard'
import { ThemeProvider } from '../../context/ThemeContext'
import BoersenpreisBlock, { baueKennzahlen } from './BoersenpreisBlock'
import { stubMatchMedia } from '../../test/render'

/** Der Chart zieht seine Achsenfarben aus dem Theme — ohne Provider wirft er. */
function zeige(daten: BoersenpreisResponse) {
  return render(<ThemeProvider><BoersenpreisBlock daten={daten} /></ThemeProvider>)
}

beforeEach(() => {
  // Der ThemeProvider fragt die Systemeinstellung ab; jsdom kennt matchMedia nicht.
  stubMatchMedia()
})

function tag(datum: string, opts: Partial<BoersenpreisTag> = {}): BoersenpreisTag {
  return {
    datum,
    stunden: Array.from({ length: 24 }, (_, h) => ({
      stunde: h,
      preis_cent: 10 + h * 0.5,
      rang: h < 5 ? h + 1 : 99,
      unter_schwelle: h < 8,
      // Abstand zum Ø dieses Tages (15,00 ct) — wie ihn die Route liefert.
      abstand_cent: Math.round((10 + h * 0.5 - 15.0) * 1000) / 1000,
    })),
    schwelle_cent: 13.5,
    optimierter_durchschnitt_cent: 15.0,
    // Ø ALLER 24 Stunden der Fixture-Reihe (10,0 … 21,5) = 15,75 — bewusst
    // ungleich dem optimierten Ø (15,0), damit ein Test die beiden Kacheln
    // nicht zufällig verwechseln kann.
    tages_durchschnitt_cent: 15.75,
    ...opts,
  }
}

function antwort(over: Partial<BoersenpreisResponse> = {}): BoersenpreisResponse {
  return {
    anlage_id: 1,
    markt: 'DE',
    tage: [tag('2026-08-06'), tag('2026-08-07')],
    monats_durchschnitt_cent: null,
    aktuelle_stunde: 3,
    heute: '2026-08-06',
    hinweis: null,
    endpreis_jetzt_cent: null,
    ...over,
  }
}

describe('baueKennzahlen', () => {
  it('nennt aktuellen Preis, Ø, Schwelle und den ct-Abstand', () => {
    const kpis = baueKennzahlen(antwort())

    // Reihenfolge = Zusage an Rainer (PN 2026-08-20): die allgemein lesbaren
    // Zahlen zuerst, die Optimierer-Werte dahinter. Der Abstand bleibt am ENDE
    // (N-173). Der Monats-Ø fehlt hier, weil die Route ihn nicht liefert —
    // dann steht dort keine Kachel statt einer 0.
    expect(kpis.map((k) => k.title)).toEqual([
      'Aktueller Preis', 'Höchstpreis heute', 'Tiefstpreis heute',
      'Ø heute', 'Ø ohne 3 Peaks', 'Günstig-Schwelle', 'Abstand zum Ø',
    ])
    expect(kpis[0].value).toBe('11,50')          // Stunde 3 → 10 + 1,5
    expect(kpis[0].subtitle).toContain('unter der Günstig-Schwelle')
  })

  it('zeigt den ct-Abstand der laufenden Stunde mit Vorzeichen (N-173)', () => {
    // Stunde 3: 11,50 ct gegen den Ø 15,00 ct ⇒ −3,50 ct/kWh. Diese Zahl gilt
    // unverändert auch für einen Endpreis mit festen Bestandteilen — genau
    // deshalb gibt es sie neben der Prozentgröße.
    const abstand = baueKennzahlen(antwort()).at(-1)!
    expect(abstand.title).toBe('Abstand zum Ø')
    expect(abstand.value).toBe('-3,50')
    expect(abstand.unit).toBe('ct/kWh')
    expect(abstand.subtitle).toContain('unter dem Ø')
  })

  it('sagt „über dem Ø", wenn die laufende Stunde teurer ist', () => {
    const abstand = baueKennzahlen(antwort({ aktuelle_stunde: 20 })).at(-1)!
    expect(abstand.value).toBe('5,00')           // 20,00 − 15,00
    expect(abstand.subtitle).toContain('über dem Ø')
  })

  it('lässt die Abstands-Kachel weg, wenn die Route sie nicht liefert', () => {
    // Alt-Stand einer laufenden Box, die noch ohne das Feld antwortet: dann
    // fehlt die Kachel, statt „0,00 ct Abstand" zu behaupten.
    const ohneAbstand = tag('2026-08-06')
    ohneAbstand.stunden = ohneAbstand.stunden.map((s) => ({ ...s, abstand_cent: null }))
    const kpis = baueKennzahlen(antwort({ tage: [ohneAbstand] }))
    expect(kpis.map((k) => k.title)).not.toContain('Abstand zum Ø')
  })

  it('zählt günstige Stunden ungekappt (N-103)', () => {
    // Acht Stunden liegen unter der Schwelle, nur fünf tragen einen Rang. Die
    // Kachel muss acht sagen — die alte, an den Rang gebundene Zahl war als
    // Divisor in einer Automation zu klein.
    const kpis = baueKennzahlen(antwort())
    const schwelle = kpis.find((k) => k.title === 'Günstig-Schwelle')!
    expect(schwelle.subtitle).toContain('8 Stunden')
  })

  it('zeigt den Tages-Ø getrennt vom optimierten Ø (rapahl-PN 23.08.)', () => {
    // Der Melder-Punkt: drei Kacheln zeigten auf den Ø OHNE die Peaks, der
    // gewöhnliche Tagesdurchschnitt fehlte ganz. Beide müssen nebeneinander
    // stehen und VERSCHIEDENE Zahlen tragen — sonst prüft der Test nichts.
    const kpis = baueKennzahlen(antwort())
    const tagesMittel = kpis.find((k) => k.title === 'Ø heute')!
    const optimiert = kpis.find((k) => k.title === 'Ø ohne 3 Peaks')!
    expect(tagesMittel.value).toBe('15,75')
    expect(optimiert.value).toBe('15,00')
    expect(tagesMittel.subtitle).toContain('aller Stunden')
    // Reihenfolge: der allgemein lesbare Wert steht VOR den Optimierer-Werten.
    expect(kpis.indexOf(tagesMittel)).toBeLessThan(kpis.indexOf(optimiert))
  })

  it('lässt den Tages-Ø weg, wenn ihn die Route nicht liefert', () => {
    const ohne = tag('2026-08-06', { tages_durchschnitt_cent: null })
    const kpis = baueKennzahlen(antwort({ tage: [ohne] }))
    expect(kpis.map((k) => k.title)).not.toContain('Ø heute')
    // ... die übrigen Kacheln bleiben davon unberührt.
    expect(kpis.map((k) => k.title)).toContain('Ø ohne 3 Peaks')
  })

  it('sagt es, wenn der aktuelle Preis über der Schwelle liegt', () => {
    const kpis = baueKennzahlen(antwort({ aktuelle_stunde: 20 }))
    expect(kpis[0].subtitle).toContain('über der Günstig-Schwelle')
  })

  it('lässt den aktuellen Preis weg, wenn seine Stunde fehlt', () => {
    // Umstellungstag: die Stunde 2 gibt es nicht. Dann steht dort auch keine
    // Kachel — statt einer 0 oder des Nachbarpreises.
    const ohneStunde2 = tag('2026-08-06')
    ohneStunde2.stunden = ohneStunde2.stunden.filter((s) => s.stunde !== 2)
    const kpis = baueKennzahlen(antwort({ tage: [ohneStunde2], aktuelle_stunde: 2 }))

    expect(kpis.map((k) => k.title)).toEqual([
      'Höchstpreis heute', 'Tiefstpreis heute', 'Ø heute', 'Ø ohne 3 Peaks', 'Günstig-Schwelle',
    ])
  })

  it('nennt Höchst- und Tiefstpreis mit ihrer Uhrzeit (Zusage rapahl)', () => {
    // Die Fixture läuft 10 + h × 0,5 ⇒ Tiefst 10,00 um 00:00, Höchst 21,50 um 23:00.
    const kpis = baueKennzahlen(antwort())
    const hoch = kpis.find((k) => k.title === 'Höchstpreis heute')!
    const tief = kpis.find((k) => k.title === 'Tiefstpreis heute')!
    expect(hoch.value).toBe('21,50')
    expect(hoch.subtitle).toBe('um 23:00 Uhr')
    expect(tief.value).toBe('10,00')
    expect(tief.subtitle).toBe('um 00:00 Uhr')
  })

  it('zeigt den Monats-Ø nur, wenn die Route ihn liefert', () => {
    // Am Monatsersten gibt es noch keine Mitschrift — dann fehlt die Kachel,
    // statt einen halben Tag als „Monatsmittel" auszugeben.
    expect(baueKennzahlen(antwort()).map((k) => k.title)).not.toContain('Ø Monat')

    const mit = baueKennzahlen(antwort({ monats_durchschnitt_cent: 14.2 }))
    const monat = mit.find((k) => k.title === 'Ø Monat')!
    expect(monat.value).toBe('14,20')
    expect(monat.subtitle).toContain('bisher aufgezeichnete')
    // …und zwar VOR den Optimierer-Werten.
    const titel = mit.map((k) => k.title)
    expect(titel.indexOf('Ø Monat')).toBeLessThan(titel.indexOf('Ø ohne 3 Peaks'))
  })

  // N-173/R2 (rapahl): der Endpreis der laufenden Stunde. Er kommt aus dem
  // zugeordneten Strompreis-Sensor — ohne ihn darf KEINE Kachel erscheinen,
  // denn ein Rückfall auf den Tarif-Arbeitspreis wäre bei dynamischem Tarif
  // ein Mittelwert im Gewand eines Stundenpreises.
  it('zeigt den Endpreis nur, wenn ein Strompreis-Sensor Werte liefert', () => {
    const ohne = baueKennzahlen(antwort())
    expect(ohne.find((k) => k.title === 'Endpreis jetzt')).toBeUndefined()

    const mit = baueKennzahlen(antwort({ endpreis_jetzt_cent: 34.7 }))
    const endpreis = mit.find((k) => k.title === 'Endpreis jetzt')!
    expect(endpreis.value).toBe('34,70')
    expect(endpreis.subtitle).toContain('Netzentgelte')

    // Er steht DIREKT hinter dem aktuellen Börsenpreis — beide beantworten
    // „was kostet jetzt", und der Aufschlag ist so ohne Rechnen ablesbar.
    const titel = mit.map((k) => k.title)
    expect(titel.indexOf('Endpreis jetzt')).toBe(titel.indexOf('Aktueller Preis') + 1)
  })

  it('zeigt keine Kennzahlen, wenn nur morgen vorliegt', () => {
    // Sie beziehen sich auf heute; die von morgen wären eine andere Aussage
    // unter demselben Titel.
    const kpis = baueKennzahlen(antwort({ tage: [tag('2026-08-07')], heute: '2026-08-06' }))
    expect(kpis).toEqual([])
  })
})

describe('BoersenpreisBlock', () => {
  it('zeigt den Hinweis, wenn morgen noch fehlt', () => {
    zeige(antwort({
      tage: [tag('2026-08-06')],
      hinweis: 'Für morgen liegen noch keine Börsenpreise vor — die Day-Ahead-Auktion veröffentlicht sie gegen 13:00 Uhr.',
    }))

    expect(screen.getByText(/Day-Ahead-Auktion veröffentlicht sie gegen 13:00/)).toBeInTheDocument()
  })

  it('nennt die Marktzone und dass die Preise netto sind', () => {
    // Ohne diesen Satz hält jemand die Kurve für seinen Lieferantenpreis.
    zeige(antwort({ markt: 'AT' }))

    expect(screen.getByText(/EPEX Österreich/)).toBeInTheDocument()
    expect(screen.getByText(/ohne Steuern, Abgaben und Netzentgelte/)).toBeInTheDocument()
  })

  it('bleibt ohne Preise stumm bis auf den Grund', () => {
    zeige(antwort({
      tage: [], aktuelle_stunde: 3, hinweis: 'Börsenpreise sind derzeit nicht abrufbar.',
    }))

    expect(screen.getByText(/nicht abrufbar/)).toBeInTheDocument()
    expect(screen.queryByText('Aktueller Preis')).not.toBeInTheDocument()
  })
})
