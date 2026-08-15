/**
 * Prognosen-Vergleich — Abweichungs-Sprache, Σ-Zeile und Zeilenfilter.
 *
 * Vier Zusagen hält dieser Test fest:
 *
 * (a) **In jeder Zeile mit gemessenem IST trägt jede Prognosespalte eine
 *     Abweichung** — auch „± 0,0". Vorher unterdrückte sich die Annotation bei
 *     |Δ| < 0,03 kWh, was je Spalte unterschiedlich zuschlug: im Bild trugen OM
 *     und SC eine Abweichung, die eedc-Spalte daneben nicht.
 *
 * (b) **Die Σ-Zeile vergleicht nur den gelaufenen Tag** (Entscheid B4). Vorher
 *     stand die Prognose des ganzen Tages gegen das IST bis jetzt — die
 *     Abweichung maß vor allem die Tageszeit.
 *
 * (c) **Dieselbe (Prognose, IST)-Paarung erzeugt in allen drei Tabellen
 *     dieselbe Annotation** (P-5 / N-50). Das ist der eigentliche Beweis der
 *     einen Sprache: vorher sagte das Genauigkeits-Tracking „+19 %", während
 *     Stundenvergleich und 7-Tage-Vergleich „▲ 0,8" sagten — über dieselben
 *     Tage, die beide Tabellen aus `genauigkeit.tage` ziehen.
 *
 * (d) **Der Zeilenfilter der 24h-Tabelle kennt die eedc-Spalte** (P-5 / N-51).
 *
 * **Spalten-Layout:** seit dem 04.08. trägt jede Quelle *zwei* Zellen — Wert und
 * Einwertung getrennt (Entscheid Gernot), damit die Prozentangabe die
 * rechtsbündige Zahl nicht mehr verschiebt. Die Tests adressieren deshalb
 * benannte Spalten, nicht Positionen im Fließtext.
 */
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'

import { Pvg24hTabelle, Pvg7TageTabelle, PvgGenauigkeitsTracking, PrognoseVergleichVM } from './PrognoseVergleichTeile'
import type { PrognosenVergleich, StundenProfilEintrag, GenauigkeitsResponse } from '../../api/aussichten'

const profil = (werte: Record<number, number | null>): StundenProfilEintrag[] =>
  Object.entries(werte).map(([h, kw]) => ({ stunde: Number(h), kw, p10_kw: null, p90_kw: null }))

/** Tagesgang mit einem Wert je Stunde 6–11 — bewusst klein, damit die
 *  Rundung auf eine Nachkommastelle nachrechenbar bleibt. */
const TAGESGANG: Record<number, number> = { 6: 0.04, 7: 0.3, 8: 0.9, 9: 2.69, 10: 3.5, 11: 5.0 }
const bis = (grenze: number, quelle = TAGESGANG) =>
  Object.fromEntries(Object.entries(quelle).filter(([h]) => Number(h) <= grenze))

const daten = (over: Partial<PrognosenVergleich> = {}): PrognosenVergleich => ({
  openmeteo_heute_kwh: 12.4, openmeteo_morgen_kwh: null, openmeteo_uebermorgen_kwh: null,
  openmeteo_tage: [], openmeteo_tageshaelften: [],
  eedc_heute_kwh: 12.0, eedc_morgen_kwh: null, eedc_uebermorgen_kwh: null,
  eedc_stundenprofil: profil(TAGESGANG), eedc_lernfaktor: 0.97, eedc_lernfaktor_stufe: 'gut',
  eedc_prognose_basis: 'eedc', eedc_tageshaelften: [],
  solcast_verfuegbar: true, solcast_status: 'ok', solcast_hinweis: null, solcast_quelle: 'api',
  solcast_heute_kwh: 11.0, solcast_p10_kwh: null, solcast_p90_kwh: null,
  solcast_morgen_kwh: null, solcast_morgen_p10_kwh: null, solcast_morgen_p90_kwh: null,
  solcast_uebermorgen_kwh: null,
  solcast_stundenprofil: profil({ ...TAGESGANG, 9: 2.39 }), solcast_tage: [], solcast_tageshaelften: [],
  ist_heute_kwh: 3.93, ist_stundenprofil: profil(bis(9)), ist_tageshaelfte: null,
  verbleibend_kwh: null, verbleibend_om_kwh: null, verbleibend_eedc_kwh: null, verbleibend_solcast_kwh: null,
  openmeteo_stundenprofil: profil(TAGESGANG),
  solcast_letzter_abruf: null, openmeteo_modell: 'icon_d2', aktuelle_stunde: 10,
  ...over,
})

/** Spalten der 24h-Tabelle. Jede Quelle: Wert, dann Einwertung.
 *  Spalte 0 ist ein Platzhalter — sie hält den Spaltenplan deckungsgleich zur
 *  7-Tage-Tabelle, die direkt darunter steht (Wetter-Symbol, Gernot 2026-08-15). */
const SP24 = { platz: 0, std: 1, om: 2, omD: 3, eedc: 4, eedcD: 5, sc: 6, scD: 7, ist: 8 } as const
/** Dieselbe Tabelle, wenn SFML die gewählte Quelle ist — eine Wertspalte mehr, kein Δ. */
const SP24_SFML = { ...SP24, sfml: 8, ist: 9 } as const
/** Spalten des Genauigkeits-Trackings (Datum, drei Quellen, IST). */
const SPTR = { datum: 0, om: 1, omD: 2, eedc: 3, eedcD: 4, sc: 5, scD: 6, ist: 7 } as const
/** Spalten der 7-Tage-Tabelle (Wetter-Icon und Datum vorweg). */
const SP7 = { wetter: 0, datum: 1, om: 2, omD: 3, eedc: 4, eedcD: 5, sc: 6, scD: 7, ist: 8 } as const
/** Dieselbe Tabelle, wenn SFML die gewählte Quelle ist — eine Wertspalte mehr. */
const SP7_SFML = { ...SP7, sfml: 8, ist: 9 } as const

const zellen = (tr: Element) => Array.from(tr.querySelectorAll('td')).map(td => td.textContent ?? '')

const zeige = (over: Partial<PrognosenVergleich> = {}) => {
  const vm = { data: daten(over) } as PrognoseVergleichVM
  const { container } = render(<Pvg24hTabelle vm={vm} />)
  return {
    stunde: (label: string) => {
      const tr = Array.from(container.querySelectorAll('tbody tr'))
        .find(r => (zellen(r)[SP24.std] ?? '') === label)
      if (!tr) throw new Error(`Stundenzeile ${label} nicht gerendert`)
      return zellen(tr)
    },
    stundenLabels: () => Array.from(container.querySelectorAll('tbody tr'))
      .map(r => zellen(r)[SP24.std] ?? ''),
    summe: () => zellen(container.querySelector('tfoot tr') as Element),
  }
}

describe('Stundenvergleich — Abweichung je Prognosespalte', () => {
  it('annotiert jede Prognosespalte, auch wenn die Abweichung 0,0 ist', () => {
    // 9:00: OM und eedc treffen das IST exakt (2,69), Solcast liegt 0,3 darunter.
    const z = zeige().stunde('9:00')

    expect(z[SP24.ist]).toBe('2,69')
    expect(z[SP24.om]).toBe('2,69')
    expect(z[SP24.omD]).toBe('± 0,0 (0 %)')
    expect(z[SP24.eedc]).toBe('2,69')
    expect(z[SP24.eedcD]).toBe('± 0,0 (0 %)')
    expect(z[SP24.sc]).toBe('2,39')
    expect(z[SP24.scD]).toBe('▼ 0,3 (11 %)')
  })

  it('lässt die Annotation weg, wo kein IST vorliegt', () => {
    // 10:00 liegt hinter der IST-Grenze — dort wäre jede Abweichung erfunden.
    const z = zeige().stunde('10:00')

    expect(z[SP24.ist]).toBe('—')
    expect(z[SP24.om]).toBe('3,50')
    expect(z[SP24.omD]).toBe('')
    expect(z[SP24.eedcD]).toBe('')
    expect(z[SP24.scD]).toBe('')
  })

  it('trägt die Prozentangabe auch bei kleinem, aber tragfähigem IST', () => {
    // 7:00: IST 0,3 — über der Referenz-Grenze 0,05, aber unter der 0,5, an der
    // das Genauigkeits-Tracking früher jede Annotation abschaltete.
    const z = zeige({ solcast_stundenprofil: profil({ ...TAGESGANG, 7: 0.14 }) }).stunde('7:00')

    expect(z[SP24.ist]).toBe('0,30')
    expect(z[SP24.scD]).toBe('▼ 0,2 (53 %)')
  })

  it('lässt die Prozentangabe weg, wo die Referenz sie nicht trägt', () => {
    // IST 0,04 liegt unter 0,05 — ein Prozentwert dagegen wäre erfunden.
    const z = zeige({ ist_stundenprofil: profil({ 6: 0.04 }), aktuelle_stunde: 6 }).stunde('6:00')

    expect(z[SP24.ist]).toBe('0,04')
    expect(z[SP24.omD]).toBe('± 0,0')
  })
})

describe('Stundenvergleich — Σ vergleicht nur den gelaufenen Tag', () => {
  it('Rumpftag: Σ endet bei der letzten Stunde mit IST und nennt sie', () => {
    const z = zeige().summe()

    // 0,04 + 0,3 + 0,9 + 2,69 = 3,93 — die Stunden 10 und 11 zählen nicht mit,
    // obwohl für sie eine Prognose vorliegt.
    expect(z[SP24.std]).toBe('Σbis 9:00')
    expect(z[SP24.ist]).toBe('3,9')
    expect(z[SP24.om]).toBe('3,9')
    expect(z[SP24.omD]).toBe('± 0,0 (0 %)')
    expect(z[SP24.eedcD]).toBe('± 0,0 (0 %)')
    // Solcast: 3,63 gegen 3,93 = 0,3 kWh = 8 %.
    expect(z[SP24.sc]).toBe('3,6')
    expect(z[SP24.scD]).toBe('▼ 0,3 (8 %)')
  })

  it('Rumpftag: die Prognose des Resttags fließt nicht in die Σ-Abweichung', () => {
    const z = zeige().summe()

    // Vor B4 stand hier die Tagessumme 12,4 gegen IST 3,9 — eine Abweichung von
    // 8,5 kWh, die nur besagte, dass der Tag noch läuft.
    expect(z[SP24.om]).not.toContain('12,4')
    expect(z[SP24.omD]).not.toContain('8,5')
  })

  it('Volltag: alle Stunden gemessen ⇒ keine Kennzeichnung, Summe wie bisher', () => {
    const alle = Object.fromEntries(Array.from({ length: 24 }, (_, h) => [h, TAGESGANG[h] ?? 0]))
    const z = zeige({
      openmeteo_stundenprofil: profil(alle), eedc_stundenprofil: profil(alle),
      solcast_stundenprofil: profil(alle), ist_stundenprofil: profil(alle),
      aktuelle_stunde: 23,
    }).summe()

    expect(z[SP24.std]).toBe('Σ')
    expect(z[SP24.ist]).toBe('12,4')
    expect(z[SP24.om]).toBe('12,4')
    expect(z[SP24.omD]).toBe('± 0,0 (0 %)')
  })

  it('Tag ohne jedes IST: volle Prognosesumme, aber kein Delta', () => {
    const z = zeige({ ist_stundenprofil: [], ist_heute_kwh: null, aktuelle_stunde: null }).summe()

    expect(z[SP24.std]).toBe('Σ')
    expect(z[SP24.ist]).toBe('—')
    expect(z[SP24.om]).toBe('12,4')
    expect(z[SP24.eedc]).toBe('12,4')
    expect(z[SP24.sc]).toBe('12,1')
    expect([z[SP24.omD], z[SP24.eedcD], z[SP24.scD]].join()).not.toMatch(/[▲▼±%]/)
  })

  it('Messlücke mitten im Tag: die Stunde fehlt in allen vier Spalten', () => {
    // 8:00 ohne Messwert (kein Zähler / Datenlücke) — die 0,9 kWh Prognose
    // dieser Stunde dürfen die Σ-Abweichung nicht als Fehlprognose belasten.
    const z = zeige({ ist_stundenprofil: profil({ ...bis(9), 8: null }) }).summe()

    expect(z[SP24.std]).toBe('Σbis 9:00')
    expect(z[SP24.ist]).toBe('3,0')
    expect(z[SP24.om]).toBe('3,0')
    expect(z[SP24.omD]).toBe('± 0,0 (0 %)')
  })
})

describe('Zeilenfilter kennt jede Quelle (N-51)', () => {
  it('zeigt eine Stunde, für die nur die eedc-Spalte einen Wert hat', () => {
    // OM und Solcast liegen auf der Filter-Schwelle, IST fehlt — nur eedc trägt.
    // Vorher fiel diese Zeile heraus, obwohl der Chart daneben sie zeichnete.
    const labels = zeige({
      openmeteo_stundenprofil: profil({ 5: 0.01, ...TAGESGANG }),
      solcast_stundenprofil: profil({ 5: 0.0, ...TAGESGANG }),
      eedc_stundenprofil: profil({ 5: 0.4, ...TAGESGANG }),
    }).stundenLabels()

    expect(labels).toContain('5:00')
  })

  it('lässt die Zeilenmenge eines normalen Tages unverändert', () => {
    // Der Tagesgang hat Werte für 6–11; alle liegen über der Schwelle, keine
    // Stunde kommt durch die eedc-Ergänzung hinzu oder fällt weg.
    expect(zeige().stundenLabels()).toEqual(['6:00', '7:00', '8:00', '9:00', '10:00', '11:00'])
  })
})

describe('SFML — gewählte Quelle wird gezeigt, aber nicht bewertet', () => {
  const mitSfml = (over: Partial<PrognosenVergleich> = {}) => daten({
    sfml_verfuegbar: true,
    sfml_heute_kwh: 11.7, sfml_morgen_kwh: 9.2, sfml_uebermorgen_kwh: null,
    sfml_stundenprofil: profil({ ...TAGESGANG, 9: 2.9 }),
    ...over,
  })

  it('bleibt ganz weg, solange SFML nicht die gewählte Quelle ist', () => {
    // Ohne `sfml_verfuegbar` darf keine Spalte erscheinen — sonst stünde bei
    // jedem Anwender eine leere Spalte für eine Quelle, die er nicht nutzt.
    const { container } = render(<Pvg24hTabelle vm={{ data: daten() } as PrognoseVergleichVM} />)
    const kopf = Array.from(container.querySelectorAll('thead th')).map(th => th.textContent ?? '')

    expect(kopf).not.toContain('SFML')
    // 9 statt 8: die führende Platzhalter-Spalte zählt mit (s. SP24).
    expect(kopf).toHaveLength(9)
  })

  it('zeigt im Stundenvergleich den SFML-Wert — und KEINE Abweichung dazu', () => {
    // Die Tom-HA-Zusage: SFML treu anzeigen ja, Genauigkeits-Ranking nein.
    // Der Beweis ist die Spaltenzahl: neun statt zehn — eine Wertspalte mehr,
    // aber kein zusätzliches Δ.
    const { container } = render(<Pvg24hTabelle vm={{ data: mitSfml() } as PrognoseVergleichVM} />)
    const kopf = Array.from(container.querySelectorAll('thead th')).map(th => th.textContent ?? '')
    const tr = Array.from(container.querySelectorAll('tbody tr'))
      .find(r => (zellen(r)[SP24.std] ?? '') === '9:00')
    if (!tr) throw new Error('Stundenzeile 9:00 nicht gerendert')
    const z = zellen(tr)

    expect(kopf).toEqual(['', 'Std.', 'OM', 'Δ', 'eedc', 'Δ', 'SC', 'Δ', 'SFML', 'IST'])
    expect(kopf.filter(k => k === 'Δ')).toHaveLength(3)
    expect(z[SP24_SFML.sfml]).toBe('2,90')          // SFML-Wert steht
    expect(z[SP24_SFML.sfml]).not.toMatch(/[▲▼±%]/) // ohne jede Einwertung
    expect(z[SP24_SFML.ist]).toBe('2,69')           // IST daneben unverändert
  })

  it('zeigt im 7-Tage-Vergleich heute und morgen, aber nichts Vergangenes', () => {
    // Für zurückliegende Tage führt eedc keine SFML-Mitschrift — genau die wäre
    // das „rolling", gegen das die Zusage geht. Die Spalte bleibt dort leer.
    const vm = { data: mitSfml(), genauigkeit: null } as PrognoseVergleichVM
    const { container } = render(<Pvg7TageTabelle vm={vm} />)
    const kopf = Array.from(container.querySelectorAll('thead th')).map(th => th.textContent ?? '')
    const heute = Array.from(container.querySelectorAll('tbody tr'))
      .find(r => zellen(r)[SP7_SFML.ist].includes('bisher'))
    if (!heute) throw new Error('Heute-Zeile nicht gerendert')

    expect(kopf).toContain('SFML')
    expect(kopf.filter(k => k === 'Δ')).toHaveLength(3)
    expect(zellen(heute)[SP7_SFML.sfml]).toBe('11,7')
    expect(zellen(heute)[SP7_SFML.sfml]).not.toMatch(/[▲▼±%]/)
  })

  it('setzt den Übermorgen-Wert aufs Datum, nicht auf die Position', () => {
    // Fehlt in der OpenMeteo-Liste ein Tag, rutscht eine positionsweise
    // Zuordnung um einen Tag weiter — der Übermorgen-Wert stünde dann beim
    // übernächsten. Die Erwartung leitet sich aus derselben Uhr ab wie der Code,
    // hängt also nicht an einem festen Datum.
    const tagPlus = (n: number) => {
      const d = new Date(`${new Date().toISOString().slice(0, 10)}T12:00:00Z`)
      d.setUTCDate(d.getUTCDate() + n)
      return d.toISOString().slice(0, 10)
    }
    const omTag = (datum: string) => ({
      datum, pv_prognose_kwh: 10.0, eedc_kwh: 10.0, wetter_symbol: 'sunny', temperatur_max_c: 20,
    })
    const vm = {
      // Übermorgen fehlt; der Tag danach ist da.
      data: mitSfml({
        sfml_uebermorgen_kwh: 7.4,
        openmeteo_tage: [omTag(tagPlus(1)), omTag(tagPlus(3))],
      } as Partial<PrognosenVergleich>),
      genauigkeit: null,
    } as PrognoseVergleichVM
    const { container } = render(<Pvg7TageTabelle vm={vm} />)
    const zeilen = Array.from(container.querySelectorAll('tbody tr')).map(r => zellen(r))

    // morgen trägt 9,2; der Übermorgen-Wert 7,4 gehört zu einem Datum, das die
    // Liste nicht enthält — er darf nirgends auftauchen. Positionsweise stünde
    // er in der letzten Zeile.
    expect(zeilen.map(z => z[SP7_SFML.sfml])).toContain('9,2')
    expect(zeilen[zeilen.length - 1][SP7_SFML.sfml]).toBe('—')
    expect(zeilen.map(z => z[SP7_SFML.sfml])).not.toContain('7,4')
  })

  it('nimmt SFML in den Zeilenfilter auf', () => {
    // Dieselbe Regel wie für eedc (N-51): eine Stunde, die nur SFML kennt,
    // gehört in die Tabelle — sonst fehlt sie ausgerechnet der Quelle, mit der
    // dieser Anwender rechnet.
    const vm = {
      data: mitSfml({
        openmeteo_stundenprofil: profil({ 5: 0.0, ...TAGESGANG }),
        solcast_stundenprofil: profil({ 5: 0.0, ...TAGESGANG }),
        eedc_stundenprofil: profil({ 5: 0.0, ...TAGESGANG }),
        sfml_stundenprofil: profil({ 5: 0.6, ...TAGESGANG }),
      }),
    } as PrognoseVergleichVM
    const { container } = render(<Pvg24hTabelle vm={vm} />)
    const labels = Array.from(container.querySelectorAll('tbody tr'))
      .map(r => zellen(r)[SP24.std] ?? '')

    expect(labels).toContain('5:00')
  })
})

describe('Eine Abweichungs-Sprache in allen drei Tabellen (N-50)', () => {
  // Bewusst weit in der Vergangenheit: `vergleichsTageVon` filtert gegen das
  // heutige Datum, und ein Test darf nicht an der Uhr der Maschine hängen.
  const TAG = '2020-06-11'
  const genauigkeit = (): GenauigkeitsResponse => ({
    anzahl_tage: 1, anzahl_ausreisser: 0, ausreisser_schwelle_prozent: 50,
    openmeteo_mae_prozent: null, openmeteo_mbe_prozent: null, openmeteo_asymmetrie: [],
    eedc_mae_prozent: null, eedc_mbe_prozent: null, eedc_asymmetrie: [],
    solcast_mae_prozent: null, solcast_mbe_prozent: null, solcast_asymmetrie: [],
    tage: [{
      datum: TAG, openmeteo_kwh: 5.0, eedc_kwh: 5.0, solcast_kwh: 5.0, ist_kwh: 4.2,
      wetter_symbol: 'cloudy', temperatur_max_c: 18, ist_ausreisser: false,
    }],
  } as unknown as GenauigkeitsResponse)

  /** Dieselbe Paarung: Prognose 5,0 gegen IST 4,2 ⇒ Δ 0,8 kWh = 19 %. */
  const ERWARTET = '▲ 0,8 (19 %)'

  it('Genauigkeits-Tracking annotiert absolut mit Prozent in Klammern', () => {
    const vm = { data: daten(), genauigkeit: genauigkeit(), ausreisserAusblenden: false } as PrognoseVergleichVM
    const { container } = render(<PvgGenauigkeitsTracking vm={vm} />)
    const z = zellen(container.querySelector('tbody tr') as Element)

    expect(z[SPTR.om]).toBe('5,0')
    expect(z[SPTR.omD]).toBe(ERWARTET)
    expect(z[SPTR.ist]).toBe('4,2')
  })

  it('7-Tage-Vergleich sagt zu demselben Tag dasselbe', () => {
    const vm = { data: daten(), genauigkeit: genauigkeit() } as PrognoseVergleichVM
    const { container } = render(<Pvg7TageTabelle vm={vm} />)
    const tr = Array.from(container.querySelectorAll('tbody tr'))
      .find(r => zellen(r)[SP7.ist] === '4,2')
    if (!tr) throw new Error('Vergangenheits-Zeile nicht gerendert')
    const z = zellen(tr)

    expect(z[SP7.om]).toBe('5,0')
    expect(z[SP7.omD]).toBe(ERWARTET)
  })

  it('Stundenvergleich sagt zu derselben Paarung dasselbe', () => {
    const z = zeige({
      openmeteo_stundenprofil: profil({ 9: 5.0 }), eedc_stundenprofil: profil({ 9: 5.0 }),
      solcast_stundenprofil: profil({ 9: 5.0 }), ist_stundenprofil: profil({ 9: 4.2 }),
      aktuelle_stunde: 9,
    }).stunde('9:00')

    expect(z[SP24.omD]).toBe(ERWARTET)
    expect(z[SP24.eedcD]).toBe(ERWARTET)
    expect(z[SP24.scD]).toBe(ERWARTET)
  })

  it('7-Tage-Vergleich: ohne gemessenes IST bleibt die Unterdrückung', () => {
    // Die Zukunfts-/Heute-Zeilen vergleichen gegen das Mittel der Prognosen —
    // dort ist ein „± 0,0" keine Aussage über die Wirklichkeit.
    const vm = { data: daten(), genauigkeit: genauigkeit() } as PrognoseVergleichVM
    const { container } = render(<Pvg7TageTabelle vm={vm} />)
    const heute = Array.from(container.querySelectorAll('tbody tr'))
      .find(r => zellen(r)[SP7.ist].includes('bisher'))
    if (!heute) throw new Error('Heute-Zeile nicht gerendert')

    // OM 12,4 · eedc 12,0 · SC 11,0 ⇒ Mittel 11,8; die Abweichungen stehen,
    // aber sie messen die Streuung der Prognosen, nicht die Wirklichkeit.
    expect(zellen(heute)[SP7.omD]).toMatch(/▲/)
  })
})

/**
 * Stundenvergleich und 7-Tage-Vergleich stehen im selben Block
 * „Tages-/Stundenprofil" **unmittelbar untereinander** — OM, eedc und SC sollen
 * dabei fluchten (Gernot 2026-08-15, gemeldet von rapahl).
 *
 * Gemessen wird der **Spaltenplan**, nicht die Optik: beide Tabellen laufen auf
 * `table-fixed`, dort bestimmt allein die `colgroup` die Spaltengrenzen. Sind
 * beide `colgroup`s zeichengleich, stehen die Spalten übereinander — ohne dass
 * ein Test Pixel messen müsste (kein Gate misst Pixel).
 *
 * Vorher trug der Stundenvergleich EINE führende Spalte (`w-16`), der
 * 7-Tage-Vergleich ZWEI (`w-20` fürs Wetter-Symbol + `w-24` fürs Datum): 64
 * gegen 176 px, und genau um diese 112 px begann die OM-Spalte weiter links (am
 * Screenshot ~110 px). Der Versatz stammt aus dem IA-V4-Umbau (`eda34e7a`,
 * v4.0.0) und fiel erst auf, als P-5 alle übrigen Spalten zur Deckung brachte.
 */
describe('Spaltenflucht: beide Tabellen tragen denselben Spaltenplan', () => {
  const spaltenplan = (c: Element) =>
    Array.from(c.querySelectorAll('colgroup col')).map(col => col.className)

  const beide = (data: PrognosenVergleich) => {
    const vm = { data, genauigkeit: null } as PrognoseVergleichVM
    return {
      stunden: spaltenplan(render(<Pvg24hTabelle vm={vm} />).container),
      tage: spaltenplan(render(<Pvg7TageTabelle vm={vm} />).container),
    }
  }

  it('deckungsgleich im Regelfall (mit Solcast, ohne SFML)', () => {
    const { stunden, tage } = beide(daten())

    expect(stunden).toEqual(tage)
    // Und die führende Spalte ist wirklich die breitere von beiden — ohne diese
    // Zeile wäre der Test auch mit zwei gleich falschen Plänen grün.
    expect(stunden.slice(0, 2)).toEqual(['w-20', 'w-24'])
  })

  it('deckungsgleich auch mit SFML als gewählter Quelle', () => {
    // Gernots Auflage vom 15.08.: die SFML-Spalte ist mit einzuplanen, sonst
    // bricht die Flucht genau bei denen, die SFML gewählt haben.
    const { stunden, tage } = beide(daten({
      sfml_verfuegbar: true,
      sfml_heute_kwh: 11.7, sfml_morgen_kwh: 9.2, sfml_uebermorgen_kwh: null,
      sfml_stundenprofil: profil({ ...TAGESGANG, 9: 2.9 }),
    }))

    expect(stunden).toEqual(tage)
  })

  it('deckungsgleich auch ohne Solcast', () => {
    const { stunden, tage } = beide(daten({ solcast_verfuegbar: false }))

    expect(stunden).toEqual(tage)
  })
})
