/**
 * Die Kapazität unter den Vollzyklen nennt dieselbe Zahl, mit der gerechnet wurde.
 *
 * ## Der Befund
 *
 * **Burkard, simon42 T89667 #276 (31.08.2026)**, an seiner eigenen Anlage
 * nachgerechnet: *„Im Speicherblock steht ‚Kapazität 8 kWh'. Gepflegt habe ich
 * 7,5 kWh, und gerechnet wird auch damit: 1.433 kWh Entladung ergeben die
 * angezeigten 191,05 Vollzyklen, mit 8 kWh wären es 179. Die Zahl stimmt also,
 * nur die Beschriftung rundet."*
 *
 * Ursache: `KomponentenSektionen` hat einen Datei-Default `fmt(v, dec = 0)`, der
 * für die kWh-Mengen daneben richtig ist — eine Speicherkapazität ist aber eine
 * feingliedrige Größe, und sie steht hier ausdrücklich als **Bezugsgröße** der
 * Vollzyklen. Zwei Zahlen, die zueinander gehören, dürfen nicht verschieden
 * gerundet sein: das ist die Klasse von **N-253** („Vergleichs-Badge bildet den
 * Prozentwert aus ungerundeten Zahlen und zeigt ihn auf 0 Stellen").
 *
 * ## Warum eine eigene Datei
 *
 * `KomponentenSektionen.test.tsx` sichert das Aktiv-Gating und die Summary-Zeile
 * der Blockfabrik. Der Untertitel der Vollzyklen-Kachel wurde von **keiner** Probe
 * behauptet (gemessen 31.08.: 0 Treffer für den Text im Testbaum) — er ist damit
 * eine eigene Aussage und kein zweiter Turm über einer bestehenden.
 *
 * ## Reichweite
 *
 * Die Zeile ist EINE Stelle, aber sie speist DREI Sichten: `TagKomponenten`,
 * `CockpitMonatV4` und `CockpitJahrV4` rufen alle dieselbe Fabrik. Deshalb prüft
 * die Datei alle drei Perioden — ein Rückbau darf nicht an einer Sicht grün
 * bleiben.
 */
import { describe, it, expect } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import type { ParkApi } from '../components/park'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import { aktuellerMonat } from '../test/factories'

const NOOP: ParkApi = {
  aktiv: false, istGeparkt: () => false, park: () => {}, entparke: () => {},
  zuruecksetzen: () => {}, geparkt: [], registriere: () => () => {}, parkbareAnzahl: 0,
}

afterEach(() => cleanup())

/**
 * Der Untertitel der Vollzyklen-Kachel in einer gewählten Periode — **gerendert**,
 * nicht am Block-Objekt abgelesen.
 *
 * ⛔ Die erste Fassung dieser Datei griff nach `block.kpis` und war rot: Die Fabrik
 * hängt die Kacheln nicht an den Block, sie steckt sie in `render()`
 * (`<Sektion kpis={…} />`). Am Objekt zu messen hätte hier nur zufällig
 * funktioniert — die Kachel entsteht erst beim Rendern, und genau die sieht der
 * Anwender. *Eine Annahme über die Form ist keine Messung der Form.*
 */
function kapazitaetsUntertitel(
  over: Partial<AktuellerMonatResponse>,
  periode: 'tag' | 'monat' | 'jahr' = 'monat',
): string | null {
  const block = baueKomponentenBloecke(aktuellerMonat(2026, 8, over), NOOP, periode)
    .find((b) => b.id === 'k-speicher')
  expect(block, 'Speicher-Block muss entstehen').toBeDefined()
  // Vor JEDEM Rendern aufräumen, nicht nur nach dem Test: Die Perioden-Schleife
  // unten ruft den Helfer dreimal, und ohne das stünden drei Speicherblöcke
  // gleichzeitig im Baum — `getByText` fiele dann über die Mehrfachtreffer,
  // nicht über den geprüften Wert.
  cleanup()
  render(<>{block!.render(false)}</>)
  // Die Kachel selbst muss da sein — sonst wäre ein fehlender Untertitel nicht von
  // einer fehlenden Kachel zu unterscheiden.
  expect(screen.getByText(/Vollzyklen/), 'Vollzyklen-Kachel muss gerendert sein').toBeInTheDocument()
  return screen.queryByText(/^Kapazität /)?.textContent ?? null
}

// Burkards Zahlen: 7,5 kWh gepflegt, 1.433 kWh Entladung ⇒ 191,05 Vollzyklen.
const BURKARD: Partial<AktuellerMonatResponse> = {
  speicher_entladung_kwh: 1433, speicher_vollzyklen: 191.05,
  speicher_kapazitaet_kwh: 7.5, hat_speicher: true,
}

describe('Speicher — die Kapazität unter den Vollzyklen rundet nicht (T89667 #276)', () => {
  it('7,5 kWh bleiben 7,5 — nicht 8', () => {
    const untertitel = kapazitaetsUntertitel(BURKARD)
    expect(untertitel).toBe('Kapazität 7,5 kWh')
    // Die Gegenrichtung ausdrücklich: genau das stand vorher da.
    expect(untertitel).not.toBe('Kapazität 8 kWh')
  })

  it('gilt in ALLEN drei Sichten — eine Zeile, drei Konsumenten', () => {
    // `TagKomponenten`, `CockpitMonatV4` und `CockpitJahrV4` rufen dieselbe Fabrik.
    // Ein Rückbau, der nur eine Sicht trifft, gibt es hier gar nicht — aber genau
    // deshalb muss die Probe es zeigen, statt es zu behaupten.
    for (const periode of ['tag', 'monat', 'jahr'] as const) {
      expect(kapazitaetsUntertitel(BURKARD, periode), periode).toBe('Kapazität 7,5 kWh')
    }
  })

  it('eine glatte Kapazität bekommt die Null, statt die Stelle zu verschlucken', () => {
    // Bewusst so: `fmtCalc` setzt min = max Nachkommastellen. „10,0 kWh" ist die
    // Schreibweise, die `SpeicherSizingIST` und `EnergieprofilPrognose` für eine
    // Speicherkapazität längst benutzen — eine Größe, eine Schreibweise.
    expect(kapazitaetsUntertitel({ ...BURKARD, speicher_kapazitaet_kwh: 10 }))
      .toBe('Kapazität 10,0 kWh')
  })

  it('ohne gepflegte Kapazität steht dort nichts — keine erfundene 0,0', () => {
    expect(kapazitaetsUntertitel({ ...BURKARD, speicher_kapazitaet_kwh: null }))
      .toBeNull()
  })
})
