/**
 * Stundenvergleich heute — Abweichungen und Σ-Zeile (Rainer PN 90004/89980).
 *
 * Zwei Zusagen hält dieser Test fest:
 *
 * (a) **In jeder Zeile mit gemessenem IST trägt jede Prognosespalte eine
 *     Abweichung** — auch „± 0,0". Vorher unterdrückte sich die Annotation bei
 *     |Δ| < 0,03 kWh, was je Spalte unterschiedlich zuschlug: im Bild trugen OM
 *     und SC eine Abweichung, die eedc-Spalte daneben nicht.
 *
 * (b) **Die Σ-Zeile vergleicht nur den gelaufenen Tag** (Entscheid B4). Vorher
 *     stand die Prognose des ganzen Tages gegen das IST bis jetzt — die
 *     Abweichung maß vor allem die Tageszeit.
 */
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'

import { Pvg24hTabelle, PrognoseVergleichVM } from './PrognoseVergleichTeile'
import type { PrognosenVergleich, StundenProfilEintrag } from '../../api/aussichten'

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

const zeige = (over: Partial<PrognosenVergleich> = {}) => {
  const vm = { data: daten(over) } as PrognoseVergleichVM
  const { container } = render(<Pvg24hTabelle vm={vm} />)
  const zellen = (tr: Element) => Array.from(tr.querySelectorAll('td')).map(td => td.textContent ?? '')
  return {
    stunde: (label: string) => {
      const tr = Array.from(container.querySelectorAll('tbody tr'))
        .find(r => (r.querySelector('td')?.textContent ?? '') === label)
      if (!tr) throw new Error(`Stundenzeile ${label} nicht gerendert`)
      return zellen(tr)
    },
    summe: () => zellen(container.querySelector('tfoot tr') as Element),
  }
}

describe('Stundenvergleich — Abweichung je Prognosespalte', () => {
  it('annotiert jede Prognosespalte, auch wenn die Abweichung 0,0 ist', () => {
    // 9:00: OM und eedc treffen das IST exakt (2,69), Solcast liegt 0,3 darunter.
    const [, om, eedc, sc, ist] = zeige().stunde('9:00')

    expect(ist).toBe('2,69')
    expect(om).toBe('2,69± 0,0')
    expect(eedc).toBe('2,69± 0,0')
    expect(sc).toBe('2,39▼ 0,3')
  })

  it('lässt die Annotation weg, wo kein IST vorliegt', () => {
    // 10:00 liegt hinter der IST-Grenze — dort wäre jede Abweichung erfunden.
    const [, om, eedc, sc, ist] = zeige().stunde('10:00')

    expect(ist).toBe('—')
    expect(om).toBe('3,50')
    expect(eedc).toBe('3,50')
    expect(sc).toBe('3,50')
  })
})

describe('Stundenvergleich — Σ vergleicht nur den gelaufenen Tag', () => {
  it('Rumpftag: Σ endet bei der letzten Stunde mit IST und nennt sie', () => {
    const [label, om, eedc, sc, ist] = zeige().summe()

    // 0,04 + 0,3 + 0,9 + 2,69 = 3,93 — die Stunden 10 und 11 zählen nicht mit,
    // obwohl für sie eine Prognose vorliegt.
    expect(label).toBe('Σbis 9:00')
    expect(ist).toBe('3,9')
    expect(om).toBe('3,9± 0,0 (0 %)')
    expect(eedc).toBe('3,9± 0,0 (0 %)')
    // Solcast: 3,63 gegen 3,93 = 0,3 kWh = 8 %.
    expect(sc).toBe('3,6▼ 0,3 (8 %)')
  })

  it('Rumpftag: die Prognose des Resttags fließt nicht in die Σ-Abweichung', () => {
    const [, om] = zeige().summe()

    // Vor B4 stand hier die Tagessumme 12,4 gegen IST 3,9 — eine Abweichung von
    // 8,5 kWh, die nur besagte, dass der Tag noch läuft.
    expect(om).not.toContain('12,4')
    expect(om).not.toContain('8,5')
  })

  it('Volltag: alle Stunden gemessen ⇒ keine Kennzeichnung, Summe wie bisher', () => {
    const alle = Object.fromEntries(Array.from({ length: 24 }, (_, h) => [h, TAGESGANG[h] ?? 0]))
    const { summe } = zeige({
      openmeteo_stundenprofil: profil(alle), eedc_stundenprofil: profil(alle),
      solcast_stundenprofil: profil(alle), ist_stundenprofil: profil(alle),
      aktuelle_stunde: 23,
    })
    const [label, om, , , ist] = summe()

    expect(label).toBe('Σ')
    expect(ist).toBe('12,4')
    expect(om).toBe('12,4± 0,0 (0 %)')
  })

  it('Tag ohne jedes IST: volle Prognosesumme, aber kein Delta', () => {
    const { summe } = zeige({ ist_stundenprofil: [], ist_heute_kwh: null, aktuelle_stunde: null })
    const [label, om, eedc, sc, ist] = summe()

    expect(label).toBe('Σ')
    expect(ist).toBe('—')
    expect(om).toBe('12,4')
    expect(eedc).toBe('12,4')
    expect(sc).toBe('12,1')
    expect([om, eedc, sc].join()).not.toMatch(/[▲▼±%]/)
  })

  it('Messlücke mitten im Tag: die Stunde fehlt in allen vier Spalten', () => {
    // 8:00 ohne Messwert (kein Zähler / Datenlücke) — die 0,9 kWh Prognose
    // dieser Stunde dürfen die Σ-Abweichung nicht als Fehlprognose belasten.
    const { summe } = zeige({ ist_stundenprofil: profil({ ...bis(9), 8: null }) })
    const [label, om, , , ist] = summe()

    expect(label).toBe('Σbis 9:00')
    expect(ist).toBe('3,0')
    expect(om).toBe('3,0± 0,0 (0 %)')
  })
})
