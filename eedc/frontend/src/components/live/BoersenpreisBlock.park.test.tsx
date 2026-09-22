/**
 * Börsenpreis-Block — die VERHALTENS-Hälfte der Element-Park-Doktrin (22.09.2026).
 *
 * Seit diesem Tag sind die neun Kennzahlen und das Diagramm **einzeln** parkbar
 * (Vorstufe des Deep-Links: wer den Block in ein HA-Dashboard einbettet, schneidet
 * ihn vorher zu). Damit gilt für ihn, was für jeden Block mit Park-Elementen gilt:
 * *ist alles geparkt, verschwindet die Hülle* — sonst bleibt die Karte samt Titel
 * und ⤢-Knopf leer im Bild stehen.
 *
 * ⛔ **Warum diese Datei neben den Wächtern steht und nicht statt ihrer.**
 * `check:park-gate` (R2) liest den Quelltext von `CockpitLiveV4.tsx` und sieht, DASS
 * die `<FokusKachel>` an einem Park-Gate hängt; `check:park-idliste` (L1/L2) hält die
 * IDs gegen ihre Erzeugungsstellen. Keiner von beiden sieht Render-Geometrie — ob die
 * Hülle sich beim Rendern wirklich zurücknimmt, steht hier. Dasselbe Argument wie in
 * `src/test/park-huelle-leer.test.tsx`.
 *
 * ⚠ **Die Grenze, ehrlich benannt:** `CockpitLiveV4` hat keine Render-Probe (es gibt
 * keine im Baum, und die Sicht zieht fünf Endpunkte im Sekundentakt). Die Hülle wird
 * hier deshalb im selben Aufbau NACHGESTELLT — echte `<Parkbar>`, echte
 * `<FokusKachel>`, echter `<BoersenpreisBlock>`, echtes `boersenpreisVollGeparkt`.
 * Deshalb steht die Regel in einer Funktion und nicht als Ausdruck im JSX: So bleibt
 * nachgestellt nur noch die eine JSX-Zeile `&& !boersenpreisAllesGeparkt`. Dass SIE
 * dort steht, ist das Einzige, was diese Datei nicht misst.
 *
 * ⛔ Und `check:park-gate` R2 fängt ihr Fehlen NICHT: Die Kachel sitzt in einer
 * `<Parkbar>`, und das erfüllt R2 schon für sich (gemessen 22.09. — der Wächter war
 * vor und nach diesem Paket mit denselben Zahlen grün). Wer die Zeile löscht, bekommt
 * keinen roten Prüfer; er bekommt eine leere Karte im Bild.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Coins } from 'lucide-react'
import type { BoersenpreisResponse, BoersenpreisTag } from '../../api/liveDashboard'
import { ThemeProvider } from '../../context/ThemeContext'
import { ParkProvider, Parkbar, usePark } from '../park'
import { FokusKachel } from '../blocks/FokusKachel'
import BoersenpreisBlock, { boersenpreisParkIds, boersenpreisVollGeparkt } from './BoersenpreisBlock'
import { stubMatchMedia } from '../../test/render'

const SICHT = 'test-boersenpreis-park'

beforeEach(() => {
  localStorage.clear()
  // Der ThemeProvider fragt die Systemeinstellung ab; jsdom kennt matchMedia nicht.
  stubMatchMedia()
})

function parke(...ids: string[]) {
  localStorage.setItem(
    'eedc-park:' + SICHT,
    JSON.stringify(ids.map((id) => ({ id, titel: id }))),
  )
}

// ── Fixture: dieselbe Reihe wie in `BoersenpreisBlock.test.tsx` ──────────────
function tag(datum: string, opts: Partial<BoersenpreisTag> = {}): BoersenpreisTag {
  return {
    datum,
    stunden: Array.from({ length: 24 }, (_, h) => ({
      stunde: h,
      preis_cent: 10 + h * 0.5,
      rang: h < 5 ? h + 1 : 99,
      unter_schwelle: h < 8,
      abstand_cent: Math.round((10 + h * 0.5 - 15.0) * 1000) / 1000,
    })),
    schwelle_cent: 13.5,
    optimierter_durchschnitt_cent: 15.0,
    tages_durchschnitt_cent: 15.75,
    ...opts,
  }
}

function antwort(over: Partial<BoersenpreisResponse> = {}): BoersenpreisResponse {
  return {
    anlage_id: 1,
    markt: 'DE',
    tage: [tag('2026-08-06'), tag('2026-08-07')],
    monats_durchschnitt_cent: 18.4,
    aktuelle_stunde: 3,
    heute: '2026-08-06',
    hinweis: null,
    endpreis_jetzt_cent: 31.2,
    ...over,
  }
}

/**
 * Die Hülle aus `CockpitLiveV4.tsx` — mit DEM Gate, das die Sicht benutzt.
 */
function Sicht({ daten }: { daten: BoersenpreisResponse }) {
  const park = usePark()
  // Dieselbe Funktion, die `CockpitLiveV4.tsx` aufruft — nachgestellt ist hier
  // allein die JSX-Zeile, nicht die Regel.
  if (boersenpreisVollGeparkt(daten, park.istGeparkt)) return null
  return (
    <Parkbar id="live:boersenpreis" titel="Börsenpreis">
      <FokusKachel titel="Börsenpreis heute & morgen" fokusId="live:boersenpreis" icon={Coins} zeigeTitel>
        <BoersenpreisBlock daten={daten} />
      </FokusKachel>
    </Parkbar>
  )
}

function zeige(daten: BoersenpreisResponse) {
  return render(
    <ThemeProvider>
      <ParkProvider persistKey={SICHT}>
        <Sicht daten={daten} />
      </ParkProvider>
    </ThemeProvider>,
  )
}

describe('Die zehn Park-IDs des Börsenpreis-Blocks', () => {
  it('nennt bei vollständigen Daten alle zehn — neun Kennzahlen und das Diagramm', () => {
    // Reihenfolge = Lesereihenfolge des Blocks; das Diagramm zuletzt.
    expect(boersenpreisParkIds(antwort())).toEqual([
      'live:boersenpreis:aktuell',
      'live:boersenpreis:endpreis-jetzt',
      'live:boersenpreis:hoechstpreis',
      'live:boersenpreis:tiefstpreis',
      'live:boersenpreis:monats-durchschnitt',
      'live:boersenpreis:tages-durchschnitt',
      'live:boersenpreis:optimierter-durchschnitt',
      'live:boersenpreis:guenstig-schwelle',
      'live:boersenpreis:abstand',
      'live:boersenpreis:chart',
    ])
  })
})

describe('Regel L2 — die ID-Liste folgt den Daten, sie steht nicht fest', () => {
  // Jede dieser Lücken ist im Feld normal. Stünden die IDs FEST in einer Liste,
  // würde `alleGeparkt` für diese Anwender nie wahr und die leere Hülle bliebe
  // stehen — der Referenzfall `ueb-schwaechen`.

  it('ohne zugeordneten Strompreis-Sensor fehlt der Endpreis', () => {
    const ids = boersenpreisParkIds(antwort({ endpreis_jetzt_cent: null }))
    expect(ids).not.toContain('live:boersenpreis:endpreis-jetzt')
    expect(ids).toContain('live:boersenpreis:aktuell')
  })

  it('ohne Preis-Mitschrift des Monats fehlt das Monatsmittel', () => {
    expect(boersenpreisParkIds(antwort({ monats_durchschnitt_cent: null })))
      .not.toContain('live:boersenpreis:monats-durchschnitt')
  })

  it('ohne aktuelle Stunde fehlen der aktuelle Preis UND der Abstand', () => {
    const ids = boersenpreisParkIds(antwort({ aktuelle_stunde: null }))
    expect(ids).not.toContain('live:boersenpreis:aktuell')
    expect(ids).not.toContain('live:boersenpreis:abstand')
  })

  it('ohne Schwelle im Tagesprofil fehlt die Günstig-Schwelle', () => {
    const ids = boersenpreisParkIds(
      antwort({ tage: [tag('2026-08-06', { schwelle_cent: null })] }),
    )
    expect(ids).not.toContain('live:boersenpreis:guenstig-schwelle')
  })

  it('liegt HEUTE nicht im Profil, bleibt nur das Diagramm', () => {
    // `baueKennzahlen` kehrt dann in der ersten Zeile leer zurück — die
    // schärfste Form des L2-Falls: neun von zehn IDs fallen auf einmal weg.
    const ids = boersenpreisParkIds(antwort({ heute: '2026-08-05' }))
    expect(ids).toEqual(['live:boersenpreis:chart'])
  })

  it('ohne Tage (nur der Grund, warum es keine Preise gibt) ist die Liste LEER', () => {
    // ADR-002/P4-Fall. Wichtig für die Gate-Zeile: `[].every()` ist `true` —
    // ohne die Längen-Hälfte verschwände genau dieser Block.
    expect(boersenpreisParkIds(antwort({ tage: [], hinweis: 'Keine Preise für morgen.' })))
      .toEqual([])
  })

  it('ohne MORGEN ändert sich an den IDs nichts — der Block ist ein Heute-Block', () => {
    // Gegenprobe zur naheliegenden Annahme, es gäbe „Morgen-IDs": Alle neun
    // Kennzahlen beziehen sich auf HEUTE; das zweite Tagesprofil zeichnet nur
    // die Kurve weiter, die schon eine ID hat.
    expect(boersenpreisParkIds(antwort({ tage: [tag('2026-08-06')] })))
      .toEqual(boersenpreisParkIds(antwort()))
  })
})

describe('Die Hülle nimmt sich zurück, wenn alles geparkt ist', () => {
  it('ungeparkt stehen Hülle, Kennzahlen und Diagramm im Bild', () => {
    const { container } = zeige(antwort())
    expect(screen.getByText('Börsenpreis heute & morgen')).toBeInTheDocument()
    expect(screen.getByText('Aktueller Preis')).toBeInTheDocument()
    expect(container.querySelector('[data-park-id="live:boersenpreis:chart"]')).not.toBeNull()
  })

  it('sind ALLE zehn geparkt, bleibt nichts stehen — kein Titel, kein ⤢-Knopf', () => {
    parke(...boersenpreisParkIds(antwort()))
    const { container } = zeige(antwort())
    expect(screen.queryByText('Börsenpreis heute & morgen')).not.toBeInTheDocument()
    // Der ⤢-Knopf ist das, was von einer leeren FokusKachel übrig BLIEBE.
    expect(container.querySelector('button[aria-label*="Fokus / Vollbild"]')).toBeNull()
    expect(container.textContent?.trim()).toBe('')
  })

  it('bleibt EINE Kennzahl ungeparkt, steht die Hülle — und nur sie darin', () => {
    const alle = boersenpreisParkIds(antwort())
    parke(...alle.filter((id) => id !== 'live:boersenpreis:tiefstpreis'))
    zeige(antwort())
    expect(screen.getByText('Börsenpreis heute & morgen')).toBeInTheDocument()
    expect(screen.getByText('Tiefstpreis heute')).toBeInTheDocument()
    expect(screen.queryByText('Aktueller Preis')).not.toBeInTheDocument()
    expect(screen.queryByText('Höchstpreis heute')).not.toBeInTheDocument()
  })

  it('bleibt NUR das Diagramm ungeparkt, steht die Hülle ebenfalls', () => {
    parke(...boersenpreisParkIds(antwort()).filter((id) => id !== 'live:boersenpreis:chart'))
    const { container } = zeige(antwort())
    expect(screen.getByText('Börsenpreis heute & morgen')).toBeInTheDocument()
    expect(container.querySelector('[data-park-id="live:boersenpreis:chart"]')).not.toBeNull()
  })

  it('ohne Preise bleibt der GRUND stehen, obwohl die ID-Liste leer ist', () => {
    // Die Längen-Hälfte der Gate-Zeile. Ohne sie wäre dieser Block ab dem
    // 22.09. unsichtbar gewesen — und zwar genau für den, dem eine Erklärung
    // zusteht (ADR-002/P4).
    zeige(antwort({ tage: [], hinweis: 'Für morgen liegen noch keine Preise vor.' }))
    expect(screen.getByText('Börsenpreis heute & morgen')).toBeInTheDocument()
    expect(screen.getByText('Für morgen liegen noch keine Preise vor.')).toBeInTheDocument()
  })
})

describe('Das Raster lässt keine leere Spalte zurück', () => {
  // Kennzahlen und Kurve stehen ab `xl` nebeneinander (⅓ / ⅔). Parkt jemand eine
  // der beiden Seiten, muss die andere die volle Breite nehmen — sonst steht das,
  // was die Park-Doktrin verhindern will, im Kleinen wieder da: eine leere Fläche.
  const spalten = (el: Element | null) => el?.className ?? ''

  it('beide sichtbar → ⅔ Kurve, ⅓ Kennzahlen', () => {
    const { container } = zeige(antwort())
    expect(spalten(container.querySelector('[data-park-id="live:boersenpreis:chart"]')))
      .toContain('xl:col-span-2')
  })

  it('Kurve geparkt → die Kennzahlen nehmen die volle Breite', () => {
    parke('live:boersenpreis:chart')
    const { container } = zeige(antwort())
    expect(container.querySelector('[data-park-id="live:boersenpreis:chart"]')).toBeNull()
    const kachel = container.querySelector('[data-park-id="live:boersenpreis:aktuell"]')
    expect(spalten(kachel?.parentElement?.parentElement ?? null)).toContain('xl:col-span-3')
  })

  it('alle Kennzahlen geparkt → die Kurve nimmt die volle Breite', () => {
    parke(...boersenpreisParkIds(antwort()).filter((id) => id !== 'live:boersenpreis:chart'))
    const { container } = zeige(antwort())
    expect(spalten(container.querySelector('[data-park-id="live:boersenpreis:chart"]')))
      .toContain('xl:col-span-3')
  })
})
