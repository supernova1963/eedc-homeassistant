/**
 * Prognosen-Vergleich nach Mitternacht — keine Doppelzeile (F-5).
 *
 * **Der gemeldete Fehler** (rapahl, 06.08.2026, Screenshots um 00:40 und 01:15
 * Ortszeit): Die 7-Tage-Liste zeigte **zwei Kalendertage mit identischen Werten
 * in allen drei Quellenspalten** — OM, eedc und Solcast, samt Solcast-Band. Es
 * war seine zweite Meldung derselben Sache; die erste war als Datenzufall
 * eingeordnet worden („der OM-Tageswert rollt und friert erst nach
 * Sonnenuntergang ein"). Das trug nicht: drei unabhängige Anbieter liefern
 * nicht zufällig dieselben drei Zahlen, und die Doppelzeile hatte **keine
 * Wetter-Ikone**, die Nachbarzeile schon.
 *
 * **Die Ursache** war `new Date().toISOString().slice(0, 10)`. `toISOString()`
 * serialisiert in UTC — zwischen 00:00 und 02:00 MESZ ist das noch gestern,
 * während das Backend seine `*_heute_kwh`-Felder für den heutigen Tag füllt.
 * Damit trug die „heute"-Zeile das Datum **D−1** mit den Werten von **D**, und
 * `zukunft` (Filter `datum > heute`) lieferte **D** gleich noch einmal. Die
 * fehlende Ikone war der Beleg: `find(om.datum === heute)` suchte D−1 in einer
 * Liste, die erst bei D beginnt.
 *
 * **Warum die Uhr gestellt wird.** Ohne `vi.setSystemTime` ist ein Test dieser
 * Art 22 von 24 Stunden grün, obwohl der Fehler drinsteckt — genau deshalb
 * haben die vorhandenen Prognose-Tests ihn nie gesehen. Die Zeitzone selbst
 * pinnt `vitest.config.ts` (`TZ: 'Europe/Berlin'`), sonst hinge der Beleg an
 * der Einstellung der Maschine.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render } from '@testing-library/react'

import { Pvg7TageTabelle, type PrognoseVergleichVM } from './PrognoseVergleichTeile'
import type { PrognosenVergleich, GenauigkeitsResponse, StundenProfilEintrag } from '../../api/aussichten'

const profil = (werte: Record<number, number | null>): StundenProfilEintrag[] =>
  Object.entries(werte).map(([h, kw]) => ({ stunde: Number(h), kw, p10_kw: null, p90_kw: null }))

/** Backend-Sicht am 2026-08-06: `*_heute_kwh` = der 06.08., Tagesliste ab 06.08. */
const daten = (): PrognosenVergleich => ({
  openmeteo_heute_kwh: 57.9, openmeteo_morgen_kwh: 45.5, openmeteo_uebermorgen_kwh: 54.8,
  openmeteo_tage: [
    { datum: '2026-08-06', pv_prognose_kwh: 57.9, eedc_kwh: 57.2, wetter_symbol: 'sonnig', temperatur_max_c: 24 },
    { datum: '2026-08-07', pv_prognose_kwh: 45.5, eedc_kwh: 44.6, wetter_symbol: 'bewoelkt', temperatur_max_c: 21.2 },
    { datum: '2026-08-08', pv_prognose_kwh: 54.8, eedc_kwh: 53.8, wetter_symbol: 'sonnig', temperatur_max_c: 24.3 },
  ] as PrognosenVergleich['openmeteo_tage'],
  openmeteo_tageshaelften: [],
  eedc_heute_kwh: 57.2, eedc_morgen_kwh: 44.6, eedc_uebermorgen_kwh: 53.8,
  eedc_stundenprofil: profil({ 10: 3.5 }), eedc_lernfaktor: 0.97, eedc_lernfaktor_stufe: 'gut',
  eedc_prognose_basis: 'eedc', eedc_tageshaelften: [],
  solcast_verfuegbar: true, solcast_status: 'ok', solcast_hinweis: null, solcast_quelle: 'api',
  solcast_heute_kwh: 53.0, solcast_p10_kwh: 33, solcast_p90_kwh: 61,
  solcast_morgen_kwh: 42.5, solcast_morgen_p10_kwh: 15, solcast_morgen_p90_kwh: 61,
  solcast_uebermorgen_kwh: 56.0,
  solcast_stundenprofil: profil({ 10: 3.4 }),
  solcast_tage: [
    { datum: '2026-08-06', kwh: 53.0, p10: 33, p90: 61 },
    { datum: '2026-08-07', kwh: 42.5, p10: 15, p90: 61 },
    { datum: '2026-08-08', kwh: 56.0, p10: 42, p90: 59 },
  ] as PrognosenVergleich['solcast_tage'],
  solcast_tageshaelften: [],
  ist_heute_kwh: 0, ist_stundenprofil: [], ist_tageshaelfte: null,
  verbleibend_kwh: null, verbleibend_om_kwh: null, verbleibend_eedc_kwh: null, verbleibend_solcast_kwh: null,
  openmeteo_stundenprofil: profil({ 10: 3.5 }),
  solcast_letzter_abruf: null, openmeteo_modell: 'icon_d2', aktuelle_stunde: 0,
} as PrognosenVergleich)

/** Historie bis einschließlich 05.08. — der Vortag ist also bekannt. */
const genauigkeit = (): GenauigkeitsResponse => ({
  anzahl_tage: 2,
  tage: [
    { datum: '2026-08-04', openmeteo_kwh: 25.0, eedc_kwh: 24.4, solcast_kwh: 42.2, ist_kwh: 31.0, ist_ausreisser: false },
    { datum: '2026-08-05', openmeteo_kwh: 49.4, eedc_kwh: 49.3, solcast_kwh: 48.2, ist_kwh: 49.0, ist_ausreisser: false },
  ],
  openmeteo_mae_prozent: 8.0, openmeteo_mbe_prozent: 4.0,
  eedc_mae_prozent: 6.0, eedc_mbe_prozent: 2.0,
  solcast_mae_prozent: 5.0, solcast_mbe_prozent: -1.0,
  openmeteo_asymmetrie: null, eedc_asymmetrie: null, solcast_asymmetrie: null,
  anzahl_ausreisser: 0, ausreisser_schwelle_prozent: 50,
} as GenauigkeitsResponse)

/** Die Komponente nimmt das ViewModel, nicht die Rohdaten. */
const vm = (): PrognoseVergleichVM => ({
  data: daten(),
  genauigkeit: genauigkeit(),
  genauigkeitsTage: 7,
  genauigkeitsModus: 'kompakt',
  ausreisserAusblenden: false,
  setGenauigkeitsTage: () => {},
  setGenauigkeitsModus: () => {},
  setAusreisserAusblenden: () => {},
  anlageId: 1,
  reload: () => {},
} as unknown as PrognoseVergleichVM)

/**
 * Die Wertezeilen EINES Render-Pfads, je Zeile als Text.
 *
 * jsdom kennt keine Media-Queries: Breit-Tabelle (`hidden sm:block`) und
 * Mobil-Karten (`sm:hidden`) stehen **beide** im DOM (so auch der Mobil-Test
 * nebenan). Wer über den ganzen Container zählt, sieht jede Zeile zweimal.
 */
function zeilenTexte(container: HTMLElement): string[] {
  const pfad = container.querySelector('.hidden.sm\\:block') ?? container
  return [...pfad.querySelectorAll('tbody tr')].map(tr => tr.textContent ?? '')
}

/** Die eine Zeile, die mit `TT.MM.` beginnt — oder `undefined`. */
const zeileMit = (container: HTMLElement, tagMonat: string) =>
  zeilenTexte(container).find(t => t.includes(tagMonat))

describe('Prognosen-Vergleich um 00:40 Ortszeit (F-5)', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  // 2026-08-06 00:40 MESZ = 2026-08-05 22:40 UTC — das Fenster der Meldung.
  const NACHTS = new Date('2026-08-05T22:40:00Z')

  it('der Vortag trägt seine EIGENEN Werte, nicht die von heute', () => {
    // Das ist der Kern des Fehlers — und die Invariante, die eine erste Fassung
    // dieses Tests verfehlt hat: Es entstehen **nicht** zwei Zeilen mit
    // demselben Datum, sondern zwei Zeilen mit verschiedenen Daten und
    // **gleichen Werten**. Mit dem UTC-Datum fiel der 05.08. aus `historisch`
    // heraus (Filter `< heute` = `< 05.08.`) und wurde durch die „heute"-Zeile
    // mit den Werten des 06.08. ersetzt.
    vi.setSystemTime(NACHTS)
    const { container } = render(<Pvg7TageTabelle vm={vm()} />)
    const vortag = zeileMit(container, '05.08.')
    expect(vortag).toBeDefined()
    expect(vortag).toContain('49,4')      // OM des 05.08. aus der Historie
    expect(vortag).not.toContain('57,9')  // …und NICHT der heutige Wert
  })

  it('keine zwei Zeilen mit identischem Wertetripel', () => {
    // Die Beobachtung aus dem Screenshot, direkt als Regel: OM, eedc und
    // Solcast dürfen sich nicht über zwei Kalendertage wiederholen.
    vi.setSystemTime(NACHTS)
    const { container } = render(<Pvg7TageTabelle vm={vm()} />)
    const tripel = zeilenTexte(container)
      .map(t => (t.match(/\d+,\d/g) ?? []).slice(0, 3).join('|'))
      .filter(t => t.split('|').length === 3)
    expect(tripel.length).toBeGreaterThan(2)
    expect(tripel.filter((t, i) => tripel.indexOf(t) !== i)).toEqual([])
  })

  it('der heutige Tag steht genau einmal', () => {
    vi.setSystemTime(NACHTS)
    const { container } = render(<Pvg7TageTabelle vm={vm()} />)
    expect(zeilenTexte(container).filter(t => t.includes('06.08.'))).toHaveLength(1)
  })

  it('tagsüber unverändert — der Fix bewegt nur das Nachtfenster', () => {
    vi.setSystemTime(new Date('2026-08-06T10:00:00Z'))
    const { container } = render(<Pvg7TageTabelle vm={vm()} />)
    const vortag = zeileMit(container, '05.08.')
    expect(vortag).toContain('49,4')
  })
})
