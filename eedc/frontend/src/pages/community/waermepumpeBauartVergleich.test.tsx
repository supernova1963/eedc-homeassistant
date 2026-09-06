import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ParkProvider } from '../../components/park/ParkContext'
import { ThemeProvider } from '../../context/ThemeContext'
import { stubMatchMedia } from '../../test/render'
import { WaermepumpeDeepDive, waermepumpeParkIds } from './CommunityKomponentenTeile'
import type {
  CommunityBenchmarkResponse,
  WPByArt,
  WPByRegion,
} from '../../api/community'

// ─── Der bauartgleiche Community-Vergleich (06.09.2026, rapahl PN 92196) ─────
//
// **Sein Fall:** Die Kachel oben vergleicht bauartspezifisch („Vergleich mit
// gleicher Bauart", SoT `lib/jazVergleich.ts`) — der Balken darunter gruppierte
// nach Bundesland und warf Luft-Wasser, Sole-Wasser und Luft-Luft in dieselben
// Werte. Seine Frage: *„Wird der JAZ aller WP-Arten gegenuebergestellt, oder
// spezifisch. Viel mehr als 3,6 sind mit einer Luft-Wasser-WP nicht wirklich
// erreichbar."*
//
// ⛔ **Diese Datei prueft ZWEI Dinge, und das ist Absicht** — es sind die beiden
// Haelften derselben Aenderung, und getrennt waere jede von ihnen gruen zu
// bekommen, ohne dass die Sache stimmt:
//
//   (1) Der Bauart-Balken erscheint und traegt die Belegzahl je Bauart.
//   (2) Die statische Park-ID-Liste stimmt mit dem gerenderten DOM ueberein.
//
// ⭐ **Warum (2) hier steht und nicht „irgendwann":** Genau diese Drift ist eine
// der drei Klassen, die bisher nur der Laufzeit-Leertest gegen eine laufende Box
// gefangen hat — eine ID-Liste, die eine andere Bedingung stellt als die
// Anzeige, laesst den Block leer-aber-sichtbar stehen. Wer ein neues Park-Element
// hinzufuegt, bringt die Probe dafuer mit, statt sie dem naechsten Release-Lauf
// zu ueberlassen.

beforeEach(() => {
  // Die Charts ziehen ihre Achsenfarben aus dem Theme; der Provider fragt die
  // Systemeinstellung ab, und jsdom kennt `matchMedia` nicht.
  stubMatchMedia()
})

const REGIONEN: WPByRegion = {
  regionen: [
    { region: 'SH', anzahl: 7, durchschnitt_jaz: 3.66, durchschnitt_stromverbrauch: null },
    { region: 'NW', anzahl: 11, durchschnitt_jaz: 2.35, durchschnitt_stromverbrauch: null },
  ],
}

// Die gemessenen Zahlen der echten Community (06.09.2026, oeffentliche API).
const ARTEN: WPByArt = {
  arten: [
    { wp_art: 'luft_wasser', label: 'Luft-Wasser', anzahl: 33, durchschnitt_jaz: 3.99 },
    { wp_art: 'sole_wasser', label: 'Sole-Wasser', anzahl: 5, durchschnitt_jaz: 3.28 },
    // ⭐ Vier Anlagen, aber KEINE bildbare Arbeitszahl — der Fall, den es real
    // gibt (alle Monate unbelastbar nach ADR-002/P12) und der seit dem
    // 06.09.2026 haeufiger wird: gerechnete Waerme sperrt die Kennzahl, laesst
    // die Anlage aber in der Community stehen.
    // ⛔ Hier stand zuerst `anzahl: 0` — damit war die Zaehl-Probe unten NICHT
    // diskriminierend: ob man ueber alle Arten oder nur ueber die belegten
    // summiert, ergab dieselbe 48. Ein Sprengsatz, der still bleibt, ist
    // teurer als gar keiner; die Fixture muss den Fall ENTHALTEN, den sie
    // behauptet.
    { wp_art: 'grundwasser', label: 'Grundwasser', anzahl: 4, durchschnitt_jaz: null },
    { wp_art: 'luft_luft', label: 'Luft-Luft', anzahl: 10, durchschnitt_jaz: 1.56 },
  ],
}

function benchmark(): CommunityBenchmarkResponse {
  return {
    anlage: { region: 'SH', wp_art: 'luft_wasser' },
    benchmark_erweitert: {
      waermepumpe: {
        jaz: { wert: 3.6, community_avg: 3.99 },
        jaz_typ: { wert: 3.6, community_avg: 3.99 },
        wp_art: 'luft_wasser',
        stromverbrauch: { wert: 2493, community_avg: 3000 },
        waermeerzeugung: { wert: 8990, community_avg: 11000 },
      },
    },
  } as unknown as CommunityBenchmarkResponse
}

function rendern(artStats: WPByArt | null) {
  return render(
    <ThemeProvider>
      <ParkProvider persistKey="test-wp-bauart">
        <WaermepumpeDeepDive
          benchmark={benchmark()}
          communityStats={REGIONEN}
          artStats={artStats}
        />
      </ParkProvider>
    </ThemeProvider>,
  )
}

describe('Community: JAZ nach Bauart', () => {
  it('zeigt den bauartgleichen Vergleich und zaehlt nur die belegten Bauarten', () => {
    rendern(ARTEN)

    expect(screen.getByText('Community: JAZ nach Bauart')).toBeInTheDocument()
    // 33 + 5 + 10 = 48 — die VIER Grundwasser-Anlagen zaehlen NICHT mit, weil
    // sie keinen Balken tragen. Die Zahl neben der Ueberschrift meint genau die
    // Menge, aus der die Balken entstanden sind; eine 52 stuende ueber einem
    // Bild, das 48 zeigt.
    expect(screen.getByText('(48 Anlagen)')).toBeInTheDocument()
  })

  // ⚠ **Was diese Datei NICHT belegen kann, ausdruecklich benannt:** die
  // Kategorie-Namen der Balken („Luft-Wasser (33)") entstehen als
  // Recharts-Achsen-Ticks und existieren in jsdom nicht
  // ([[reference_recharts_bars_jsdom]]). Dass die Belegzahl je Bauart im Bild
  // steht statt im Hover, ist hier also NICHT gemessen — das sieht erst der
  // Blick auf die laufende Box. Eine Probe, die so tut, als koenne sie es,
  // waere schlimmer als keine.

  it('laesst eine Bauart ohne bildbare Arbeitszahl weg statt sie mit 0 zu zeigen', () => {
    rendern(ARTEN)
    // `grundwasser` hat vier Anlagen, aber keine bildbare JAZ. Ein Balken auf 0
    // waere die Behauptung „gemessen, und zwar schlecht" (ADR-002/P4) — und
    // wuerde den Bauart-Schnitt nach unten ziehen.
    expect(screen.queryByText(/Grundwasser/)).not.toBeInTheDocument()
  })

  it('rendert den Block gar nicht, wenn nur EINE Bauart belegt ist', () => {
    // Ein „Vergleich" mit sich selbst ist keiner — und ein Balken mit einem
    // Balken sagt nichts ueber Bauarten aus.
    rendern({
      arten: [
        { wp_art: 'luft_wasser', label: 'Luft-Wasser', anzahl: 33, durchschnitt_jaz: 3.99 },
        { wp_art: 'sole_wasser', label: 'Sole-Wasser', anzahl: 0, durchschnitt_jaz: null },
      ],
    })
    expect(screen.queryByText('Community: JAZ nach Bauart')).not.toBeInTheDocument()
  })

  it('rendert den Block nicht, wenn der Server die Bauart-Sicht nicht liefert', () => {
    rendern(null)
    expect(screen.queryByText('Community: JAZ nach Bauart')).not.toBeInTheDocument()
    // Gegenprobe: der Rest der Sicht steht weiterhin.
    expect(screen.getByText('Community: JAZ nach Region')).toBeInTheDocument()
  })
})

describe('JAZ nach Region: der Balken zeigt nicht mehr die BESTEN Regionen', () => {
  // ⛔ Bis zum 06.09.2026 sortierte der Balken nach JAZ absteigend und schnitt
  // mit `.slice(0, 10)` — er zeigte damit die zehn BESTEN Regionen. Am selben
  // Tag an der oeffentlichen API gemessen: von dreizehn Regionen mit Wert
  // fielen genau die drei schwaechsten heraus (BY 1,64 · HE 0,98 · BE 0,00).
  // Jede Region rutschte in diesem Bild systematisch nach unten — und rapahls
  // Frage entstand genau daran.
  const dreizehn = (): WPByRegion => ({
    regionen: Array.from({ length: 13 }, (_, i) => ({
      region: `R${i}`,
      // R0 hat den hoechsten JAZ und die WENIGSTEN Anlagen, R12 umgekehrt —
      // so trennen die beiden Sortierungen sauber.
      anzahl: i + 1,
      durchschnitt_jaz: 6.5 - i * 0.4,
      durchschnitt_stromverbrauch: null,
    })),
  })

  function mitRegionen(regionen: WPByRegion, eigene: string) {
    const b = benchmark()
    ;(b.anlage as { region: string }).region = eigene
    return render(
      <ThemeProvider>
        <ParkProvider persistKey="test-wp-region">
          <WaermepumpeDeepDive benchmark={b} communityStats={regionen} artStats={null} />
        </ParkProvider>
      </ThemeProvider>,
    )
  }

  it('waehlt nach Belegdichte, nicht nach Rang', () => {
    mitRegionen(dreizehn(), 'R12')
    // Zehn Regionen mit den meisten Anlagen: R3..R12 (anzahl 4..13) = 85.
    // Die alte Regel haette R0..R9 gewaehlt (anzahl 1..10) = 55 und damit die
    // drei bestbelegten Regionen weggelassen.
    expect(screen.getByText('(85 Anlagen)')).toBeInTheDocument()
  })

  it('zeigt die EIGENE Region auch dann, wenn sie duenn belegt ist', () => {
    // R0 hat genau eine Anlage und faellt aus den Top-10 nach Belegdichte —
    // sie ist aber der Bezugspunkt des Anwenders. Ohne sie zeigt das Bild
    // alles ausser dem, wofuer er es geoeffnet hat.
    mitRegionen(dreizehn(), 'R0')
    expect(screen.getByText('(86 Anlagen)')).toBeInTheDocument()
  })
})

describe('Park-ID-Liste stimmt mit dem gerenderten DOM ueberein', () => {
  // Die Drift-Probe. `waermepumpeParkIds` ist eine HANDGEPFLEGTE Liste, das
  // DOM ist die Wahrheit — weichen sie ab, bleibt ein Block leer-aber-sichtbar
  // stehen (er haelt sich fuer belegt) oder er verschwindet zu frueh.
  const gerenderteIds = (container: HTMLElement) =>
    [...container.querySelectorAll('[data-park-id]')]
      .map((e) => e.getAttribute('data-park-id'))
      .filter((id): id is string => !!id)
      .sort()

  it('mit Bauart-Sicht: die Liste nennt genau die gerenderten IDs', () => {
    const { container } = rendern(ARTEN)
    const behauptet = waermepumpeParkIds(benchmark(), REGIONEN, ARTEN).sort()

    expect(behauptet).toContain('komp-wp-chart-bauart')
    expect(gerenderteIds(container)).toEqual(behauptet)
  })

  it('ohne Bauart-Sicht: die Liste nennt die ID NICHT', () => {
    const { container } = rendern(null)
    const behauptet = waermepumpeParkIds(benchmark(), REGIONEN, null).sort()

    expect(behauptet).not.toContain('komp-wp-chart-bauart')
    expect(gerenderteIds(container)).toEqual(behauptet)
  })
})
