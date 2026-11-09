/**
 * Prognosen-Vergleich auf dem Handy — Karten statt Wegnahme (N-127).
 *
 * Bis v4.0.8 stand um KPI-Matrix, Genauigkeits-Tracking und 7-Tage-Vergleich
 * ein `DatendichtFallback`: unter `sm` ersetzte er die Tabelle durch einen
 * Hinweiskasten („bitte Gerät ins Querformat drehen oder Desktop verwenden"),
 * im Querformat durch „Auflösung zu gering". Der Inhalt war mobil **nicht**
 * erreichbar — was die Mobile-Regel ausschließt (Gernot, 2026-05-31:
 * „nichts wird auf Mobile unerreichbar, nur de-priorisiert").
 *
 * jsdom hat keine Media-Queries: geprüft wird deshalb, dass **beide**
 * Render-Pfade im DOM stehen (Tabelle in `hidden sm:block`, Karten in
 * `sm:hidden`) und dass die Karten dieselben Zahlen tragen wie die Tabelle.
 * Der Hinweistext selbst darf nirgends mehr vorkommen — das ist die Zusage.
 *
 * Dazu N-128: die relative Abweichung ist gekappt, und N-782: der Zeitpunkt-Umschalter des
 * Genauigkeits-Trackings samt «nicht erhoben» (Backend-Seite: `test_genauigkeit_zeitpunkt.py`).
 */
import { describe, it, expect } from 'vitest'
import { render, fireEvent, within } from '@testing-library/react'

import {
  PvgKpiMatrix, Pvg7TageTabelle, PvgGenauigkeitsTracking, PrognoseVergleichVM,
} from './PrognoseVergleichTeile'
import type { PrognosenVergleich, GenauigkeitsResponse, StundenProfilEintrag } from '../../api/aussichten'

const profil = (werte: Record<number, number | null>): StundenProfilEintrag[] =>
  Object.entries(werte).map(([h, kw]) => ({ stunde: Number(h), kw, p10_kw: null, p90_kw: null }))

const daten = (over: Partial<PrognosenVergleich> = {}): PrognosenVergleich => ({
  openmeteo_heute_kwh: 12.4, openmeteo_morgen_kwh: 9.1, openmeteo_uebermorgen_kwh: 7.7,
  openmeteo_tage: [], openmeteo_tageshaelften: [],
  eedc_heute_kwh: 12.0, eedc_morgen_kwh: 8.8, eedc_uebermorgen_kwh: 7.4,
  eedc_stundenprofil: profil({ 10: 3.5 }), eedc_lernfaktor: 0.97, eedc_lernfaktor_stufe: 'gut',
  eedc_prognose_basis: 'eedc', eedc_tageshaelften: [],
  solcast_verfuegbar: true, solcast_status: 'ok', solcast_hinweis: null, solcast_quelle: 'api',
  solcast_heute_kwh: 11.0, solcast_p10_kwh: null, solcast_p90_kwh: null,
  solcast_morgen_kwh: 8.2, solcast_morgen_p10_kwh: null, solcast_morgen_p90_kwh: null,
  solcast_uebermorgen_kwh: 6.9,
  solcast_stundenprofil: profil({ 10: 3.4 }), solcast_tage: [],
  solcast_tageshaelften: [null, { vormittag_kwh: 8.2, nachmittag_kwh: 0.0 }, null],
  ist_heute_kwh: 3.93, ist_stundenprofil: profil({ 9: 2.69 }), ist_tageshaelfte: null,
  verbleibend_kwh: null, verbleibend_om_kwh: null, verbleibend_eedc_kwh: null, verbleibend_solcast_kwh: null,
  openmeteo_stundenprofil: profil({ 10: 3.5 }),
  solcast_letzter_abruf: null, openmeteo_modell: 'icon_d2', aktuelle_stunde: 10,
  ...over,
})

const genauigkeit = (over: Partial<GenauigkeitsResponse> = {}): GenauigkeitsResponse => ({
  anzahl_tage: 2,
  tage: [
    { datum: '2026-08-03', openmeteo_kwh: 14.0, eedc_kwh: 13.6, solcast_kwh: 12.9, ist_kwh: 12.0, ist_ausreisser: false },
    { datum: '2026-08-04', openmeteo_kwh: 11.0, eedc_kwh: 10.7, solcast_kwh: 10.2, ist_kwh: 10.5, ist_ausreisser: false },
  ],
  openmeteo_mae_prozent: 8.0, openmeteo_mbe_prozent: 4.0,
  eedc_mae_prozent: 6.0, eedc_mbe_prozent: 2.0,
  solcast_mae_prozent: 5.0, solcast_mbe_prozent: -1.0,
  openmeteo_asymmetrie: null, eedc_asymmetrie: null, solcast_asymmetrie: null,
  anzahl_ausreisser: 0, ausreisser_schwelle_prozent: 50,
  ...over,
} as GenauigkeitsResponse)

const vmVon = (over: Partial<PrognosenVergleich> = {}, g?: GenauigkeitsResponse) => ({
  data: daten(over),
  genauigkeit: g ?? genauigkeit(),
  genauigkeitsTage: 7,
  genauigkeitsModus: 'kompakt',
  genauigkeitsZeitpunkt: 'day_ahead',
  ausreisserAusblenden: false,
  setGenauigkeitsTage: () => {},
  setGenauigkeitsModus: () => {},
  setGenauigkeitsZeitpunkt: () => {},
  setAusreisserAusblenden: () => {},
  anlageId: 1,
  reload: () => {},
} as unknown as PrognoseVergleichVM)

/** Der mobile Pfad: alles unterhalb eines `sm:hidden`-Containers. */
const mobilText = (container: HTMLElement): string =>
  Array.from(container.querySelectorAll('.sm\\:hidden')).map(e => e.textContent ?? '').join(' ')

/** Der Breit-Pfad: die Tabelle, versteckt bis `sm`. */
const breitContainer = (container: HTMLElement) => container.querySelector('.hidden.sm\\:block')

describe('Prognosen-Vergleich mobil — beide Render-Pfade, kein Wegsperren', () => {
  it.each([
    ['KPI-Matrix', (vm: PrognoseVergleichVM) => <PvgKpiMatrix vm={vm} />],
    ['Genauigkeits-Tracking', (vm: PrognoseVergleichVM) => <PvgGenauigkeitsTracking vm={vm} />],
    ['7-Tage-Vergleich', (vm: PrognoseVergleichVM) => <Pvg7TageTabelle vm={vm} />],
  ])('%s: Tabelle ab sm UND Karten darunter', (_name, renderBlock) => {
    const { container } = render(renderBlock(vmVon()))

    const breit = breitContainer(container)
    expect(breit, 'die Tabelle bleibt der Breit-Pfad').not.toBeNull()
    expect(breit!.querySelector('table')).not.toBeNull()

    // Die Karten stehen daneben — und tragen echte Werte, keinen Ersatztext.
    const mobil = mobilText(container)
    expect(mobil.length).toBeGreaterThan(0)
    expect(mobil).not.toMatch(/Querformat|Desktop verwenden|Auflösung zu gering/)
  })

  it('der Ersatztext ist nirgends mehr im DOM', () => {
    for (const block of [
      <PvgKpiMatrix vm={vmVon()} key="a" />,
      <PvgGenauigkeitsTracking vm={vmVon()} key="b" />,
      <Pvg7TageTabelle vm={vmVon()} key="c" />,
    ]) {
      const { container } = render(block)
      expect(container.textContent).not.toMatch(/bitte Gerät ins Querformat drehen/)
    }
  })

  it('KPI-Matrix: je Tag eine Karte mit allen Quellen', () => {
    const { container } = render(<PvgKpiMatrix vm={vmVon()} />)
    const mobil = mobilText(container)

    expect(mobil).toContain('Heute')
    expect(mobil).toContain('Morgen')
    expect(mobil).toContain('Übermorgen')
    // Dieselben Zahlen wie in der Tabelle — Morgen über alle drei Quellen.
    expect(mobil).toContain('9,1')   // OpenMeteo
    expect(mobil).toContain('8,8')   // eedc
    expect(mobil).toContain('8,2')   // Solcast
    // Die Tageshälften reisen als Zusatz mit, statt zu verschwinden.
    expect(mobil).toContain('VM/NM')
  })

  it('Genauigkeits-Tracking: Karte je Tag mit Abweichung je Quelle', () => {
    const { container } = render(<PvgGenauigkeitsTracking vm={vmVon()} />)
    const mobil = mobilText(container)

    // 04.08.: OM 11,0 gegen IST 10,5 → ▲ 0,5 (5 %)
    expect(mobil).toContain('IST 10,5')
    expect(mobil).toContain('▲ 0,5 (5 %)')
  })

  it('7-Tage-Vergleich: Karte je Tag, SFML ohne Δ', () => {
    const { container } = render(
      <Pvg7TageTabelle vm={vmVon({ sfml_verfuegbar: true } as Partial<PrognosenVergleich>)} />
    )
    const mobil = mobilText(container)

    expect(mobil).toContain('OM')
    expect(mobil).toContain('Solcast')
    expect(mobil).toContain('SFML')
  })
})

describe('N-128 — die relative Abweichung ist gekappt', () => {
  it('zeigt „> 999 %" statt einer vierstelligen Prozentzahl', () => {
    // Ausfalltag: IST 0,2 kWh, Prognosen im normalen Bereich.
    const g = genauigkeit({
      tage: [
        { datum: '2026-08-04', openmeteo_kwh: 5.0, eedc_kwh: 4.8, solcast_kwh: 4.5, ist_kwh: 0.2, ist_ausreisser: false },
      ],
    } as Partial<GenauigkeitsResponse>)
    const { container } = render(<PvgGenauigkeitsTracking vm={vmVon({}, g)} />)

    expect(container.textContent).toContain('> 999 %')
    expect(container.textContent).not.toMatch(/\(\d{4,} %\)/)
    // Der absolute Wert bleibt unangetastet — dort steht die Größenordnung.
    expect(container.textContent).toContain('▲ 4,8')
  })

  it('lässt gewöhnliche Prozentzahlen unverändert', () => {
    const { container } = render(<PvgGenauigkeitsTracking vm={vmVon()} />)

    expect(container.textContent).toContain('(5 %)')
    expect(container.textContent).not.toContain('> 999 %')
  })
})

describe('N-782 — Genauigkeits-Tracking: Zeitpunkt «Day-Ahead | Abend»', () => {
  it('zeigt den Umschalter mit Day-Ahead als gewähltem Stand und reicht den Wechsel an das VM', () => {
    const gesetzt: string[] = []
    const v = { ...vmVon(), setGenauigkeitsZeitpunkt: (z: string) => gesetzt.push(z) } as unknown as PrognoseVergleichVM
    const { getByRole } = render(<PvgGenauigkeitsTracking vm={v} />)
    const gruppe = getByRole('group', { name: 'Zeitpunkt' })
    expect(within(gruppe).getByRole('button', { name: 'Day-Ahead' }).getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(within(gruppe).getByRole('button', { name: 'Abend' }))
    expect(gesetzt).toEqual(['abend'])
  })

  it('erklärt, was die zwei Zeitpunkte messen — und hängt die eedc-Spalte an keinen Lernfaktor', () => {
    const { container } = render(<PvgGenauigkeitsTracking vm={vmVon({ eedc_lernfaktor: null })} />)
    expect(container.textContent).toContain('Day-Ahead = Stand in der Nacht')
    expect(container.textContent).toContain('per Satellit')
    expect(container.textContent).not.toContain('Lernfaktor noch nicht verfügbar')
  })

  it('zeigt einen Tag ohne aufgezeichneten Stand als «nicht erhoben», in Tabelle und Karte', () => {
    const g = genauigkeit({
      tage: [
        { datum: '2026-08-04', openmeteo_kwh: 11.0, eedc_kwh: null, solcast_kwh: 10.2, ist_kwh: 10.5, ist_ausreisser: false },
      ],
    } as Partial<GenauigkeitsResponse>)
    const { container } = render(<PvgGenauigkeitsTracking vm={vmVon({}, g)} />)
    expect(breitContainer(container)?.textContent).toContain('nicht erhoben')
    expect(mobilText(container)).toContain('nicht erhoben')
  })
})

describe('Päckchen CC — Zeitpunkt «Mittag», Quellen-Empfehlung, Korrektur-Wächter', () => {
  it('bietet «Mittag» als dritten Zeitpunkt an und erklärt ihn', () => {
    const gesetzt: string[] = []
    const v = { ...vmVon(), setGenauigkeitsZeitpunkt: (z: string) => gesetzt.push(z) } as unknown as PrognoseVergleichVM
    const { getByRole, container } = render(<PvgGenauigkeitsTracking vm={v} />)
    fireEvent.click(within(getByRole('group', { name: 'Zeitpunkt' })).getByRole('button', { name: 'Mittag' }))
    expect(gesetzt).toEqual(['mittag'])
    expect(container.textContent).toContain('Mittag = der Stand um 12 Uhr')
  })

  it('nennt die beste Quelle aus dem Backend und den Weg zu Solcast, wenn Solcast nicht gewählt ist', () => {
    const g = genauigkeit({ beste_quelle: 'solcast', beste_quelle_mae_prozent: 12.8, eedc_mae_prozent: 15.5, prognose_quelle: 'eedc' })
    const { container } = render(<PvgGenauigkeitsTracking vm={vmVon({}, g)} />)
    expect(container.textContent).toContain('Zum Zeitpunkt Day-Ahead trifft an dieser Anlage Solcast am besten (MAE 12,8 % gegen eedc 15,5 %).')
    expect(container.textContent).toContain('Solcast kann unter Einstellungen')
  })

  it('ohne Zusatz, wenn eedc vorn ist oder Solcast schon gewählt — ohne Empfehlung kein Satz', () => {
    const vorn = render(<PvgGenauigkeitsTracking vm={vmVon({}, genauigkeit({ beste_quelle: 'eedc', beste_quelle_mae_prozent: 6.0 }))} />)
    expect(vorn.container.textContent).toContain('trifft an dieser Anlage eedc am besten (MAE 6,0 %).')
    vorn.unmount()
    const gewaehlt = render(<PvgGenauigkeitsTracking vm={vmVon({}, genauigkeit({ beste_quelle: 'solcast', beste_quelle_mae_prozent: 5.0, prognose_quelle: 'solcast' }))} />)
    expect(gewaehlt.container.textContent).not.toContain('Solcast kann unter Einstellungen')
    gewaehlt.unmount()
    const ohne = render(<PvgGenauigkeitsTracking vm={vmVon()} />)
    expect(ohne.container.textContent).not.toContain('am besten')
  })

  it('zeigt die Kopfzeile des Wächters nur, wenn die Korrektur ausgesetzt ist', () => {
    const aus = genauigkeit({ korrektur_status: { ausgesetzt: true, mae_kaskade_prozent: 24.0, mae_roh_prozent: 21.0, tage: 30 } })
    const { container, unmount } = render(<PvgGenauigkeitsTracking vm={vmVon({}, aus)} />)
    expect(container.textContent).toContain('Korrektur ausgesetzt — die letzten 30 Tage war die Korrektur schlechter als OpenMeteo roh (MAE 24,0 % gegen 21,0 %)')
    unmount()
    const an = genauigkeit({ korrektur_status: { ausgesetzt: false, mae_kaskade_prozent: 18.0, mae_roh_prozent: 21.0, tage: 30 } })
    expect(render(<PvgGenauigkeitsTracking vm={vmVon({}, an)} />).container.textContent).not.toContain('Korrektur ausgesetzt')
  })
})
