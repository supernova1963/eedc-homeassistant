/**
 * LiveAufEinenBlick — der „Auf einen Blick"-Block neben dem Energiefluss-SVG
 * (IA-V4, Cockpit/Live).
 *
 * EIN Container mit EINER Vollbild-Funktion statt der früheren fünf einzeln
 * verschachtelten Fokus-Kacheln (je Element eine eigene FokusKachel). Die
 * verschachtelten „Container mit Vollbild" zerlegten das saubere Stapeln rechts
 * neben dem SVG — nur „Heute" saß richtig, der Rest verrutschte nach unten
 * (detLAN, 2026-06-28; Vorschlag Gernot: ein Block, ausblendbare Abschnitte).
 *
 * Ausblenden über die bestehende Element-Park-Mechanik (Rechtsklick / Long-Press
 * → Parkplatz auf Seiten-Ebene), NICHT über einen Sonder-Schalter: jeder
 * Abschnitt (Heute · Sonnenstand · Solar-Aussicht · Ladezustand · Temperaturen)
 * ist mit {@link Parkbar} umhüllt, der seitenweite {@link ParkFuss} (in
 * CockpitLiveV4) holt geparkte Abschnitte zurück. Nicht-verfügbare Abschnitte
 * (keine Daten) erscheinen gar nicht. Die geteilten `live/*`-Sub-Komponenten
 * bleiben unverändert (eine Code-Wahrheit mit der IST-v3-Live-Sicht).
 */
import type { ReactNode } from 'react'
import { Calendar, Sunrise, Sun, Battery, Thermometer, Gauge, LayoutGrid } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { FokusKachel } from '../blocks'
import { Parkbar, usePark } from '../park'
import LiveHeuteKacheln from './LiveHeuteKacheln'
import SunProgressBar from './SunProgressBar'
import SolarAussicht3Tage from './SolarAussicht3Tage'
import LiveSocBalken from './LiveSocBalken'
import LiveTemperaturen from './LiveTemperaturen'
import LiveZaehlerstaende from './LiveZaehlerstaende'
import LiveInnengeraete from './LiveInnengeraete'
import type { LiveDashboardResponse, LiveWetterResponse } from '../../api/liveDashboard'
import type { SolarPrognoseTag } from '../../api/wetter'
import type { ZaehlerStand } from '../../api/zaehlerstaende'

interface Abschnitt {
  key: AbschnittKey
  titel: string
  icon: LucideIcon
  /** Bringt die Sub-Komponente ihre eigene Überschrift mit? Sonst ergänzen wir eine. */
  eigenerTitel: boolean
  verfuegbar: boolean
  render: () => ReactNode
}

/** Die Abschnitte dieses Blocks — Park-IDs sind `live:<key>`. */
export type AbschnittKey =
  | 'heute' | 'sonnenstand' | 'solar-aussicht' | 'ladezustand'
  | 'temperaturen' | 'zaehlerstaende' | 'innengeraete'

export interface AufEinenBlickDaten {
  data: LiveDashboardResponse
  wetter: LiveWetterResponse | null
  prognose3Tage: SolarPrognoseTag[] | null
  zaehlerstaende?: ZaehlerStand[]
}

/**
 * Welche Abschnitte erscheinen unter diesen Daten überhaupt?
 *
 * Eigene Funktion, weil die Antwort an ZWEI Stellen gebraucht wird: hier für das
 * Rendern — und in `CockpitLiveV4` für die Deep-Link-Degradation (FD-5). Ein
 * `#/cockpit/live?fokus=live:auf-einen-blick` muss wissen, ob es diesen Block
 * gerade gibt; die Sicht kann das nicht raten, ohne die Regeln zu kopieren.
 */
export function aufEinenBlickVerfuegbar({ data, wetter, prognose3Tage, zaehlerstaende }: AufEinenBlickDaten): Set<AbschnittKey> {
  const keys: AbschnittKey[] = ['heute']
  if (wetter?.sunrise && wetter?.sunset) keys.push('sonnenstand')
  if (prognose3Tage && prognose3Tage.length > 0) keys.push('solar-aussicht')
  if (data.gauges?.some((g) => g.key.startsWith('soc_'))) keys.push('ladezustand')
  if (wetter?.aktuell?.temperatur_c != null || data.warmwasser_temperatur_c != null) keys.push('temperaturen')
  // #377: Der Abschnitt erscheint nur, wenn wirklich ein Stand vorliegt — ein
  // angelegter Zähler ohne Messung bekäme sonst eine leere Kachel.
  if (zaehlerstaende?.some((z) => z.stand_ende != null)) keys.push('zaehlerstaende')
  // #263: dieselbe Regel wie beim Zähler — ein angelegtes Innengerät ohne
  // jeden Wert bekommt keine leere Kachel.
  if (data.innengeraete?.some((g) => g.leistung_w != null || g.ist_temperatur_c != null || g.soll_temperatur_c != null)) {
    keys.push('innengeraete')
  }
  return new Set(keys)
}

/**
 * Park-Doktrin R2: Sind ALLE verfügbaren Abschnitte geparkt, verschwindet die
 * ganze Hülle (sonst bliebe ein leerer Kachel-Kopf stehen). Zugleich die
 * FD-5-Bedingung der Sicht: dann gibt es nichts zu fokussieren.
 *
 * ⚠ Eine LEERE Menge zählt NICHT als „alles geparkt" — `heute` ist immer
 * verfügbar, die Menge ist also nie leer; die Prüfung steht trotzdem da, weil
 * derselbe Fehler den Börsenpreis-Block einmal unsichtbar gemacht hätte.
 */
export function aufEinenBlickVollGeparkt(d: AufEinenBlickDaten, istGeparkt: (id: string) => boolean): boolean {
  // ⚠ Die Liste wird aus den DATEN abgeleitet, nie fest geschrieben — genau das
  // verlangt `check:park-idliste` (L2): eine feste Liste, die eine nur bedingt
  // gerenderte ID nennt, macht `alleGeparkt` nie wahr.
  const ids = [...aufEinenBlickVerfuegbar(d)].map((k) => `live:${k}`)
  return ids.length > 0 && ids.every((id) => istGeparkt(id))
}

export default function LiveAufEinenBlick({ data, wetter, prognose3Tage, zaehlerstaende }: {
  data: LiveDashboardResponse
  wetter: LiveWetterResponse | null
  prognose3Tage: SolarPrognoseTag[] | null
  /** #377 — Verbrauchszähler (Gas/Wasser/Öl). Leer, wenn keiner gepflegt ist. */
  zaehlerstaende?: ZaehlerStand[]
}) {
  const park = usePark()
  const verfuegbar = aufEinenBlickVerfuegbar({ data, wetter, prognose3Tage, zaehlerstaende })

  const abschnitte: Abschnitt[] = [
    {
      key: 'heute', titel: 'Heute', icon: Calendar, eigenerTitel: true, verfuegbar: verfuegbar.has('heute'),
      render: () => <LiveHeuteKacheln data={data} />,
    },
    {
      key: 'sonnenstand', titel: 'Sonnenstand', icon: Sunrise, eigenerTitel: false, verfuegbar: verfuegbar.has('sonnenstand'),
      render: () => (
        <SunProgressBar
          sunrise={wetter!.sunrise!}
          sunset={wetter!.sunset!}
          solar_noon={wetter!.solar_noon ?? undefined}
          sonnenstunden={wetter!.sonnenstunden}
          sonnenstundenBisher={wetter!.sonnenstunden_bisher}
          sonnenstundenRest={wetter!.sonnenstunden_rest}
        />
      ),
    },
    {
      key: 'solar-aussicht', titel: 'Solar-Aussicht', icon: Sun, eigenerTitel: true, verfuegbar: verfuegbar.has('solar-aussicht'),
      render: () => <SolarAussicht3Tage prognose3Tage={prognose3Tage!} wetter={wetter} heutePvKwh={data.heute_pv_kwh} />,
    },
    {
      key: 'ladezustand', titel: 'Ladezustand', icon: Battery, eigenerTitel: true, verfuegbar: verfuegbar.has('ladezustand'),
      render: () => <LiveSocBalken gauges={data.gauges} />,
    },
    {
      key: 'temperaturen', titel: 'Temperaturen', icon: Thermometer, eigenerTitel: false, verfuegbar: verfuegbar.has('temperaturen'),
      render: () => (
        <LiveTemperaturen
          aussenC={wetter?.aktuell?.temperatur_c}
          tempMinC={wetter?.temperatur_min_c}
          tempMaxC={wetter?.temperatur_max_c}
          warmwasserC={data.warmwasser_temperatur_c}
        />
      ),
    },
    {
      // #377 — direkt unter *Temperaturen*, und zwar aus demselben Grund:
      // beides sind Werte, die eedc anzeigt, ohne sie zu verrechnen.
      key: 'zaehlerstaende', titel: 'Zählerstände', icon: Gauge, eigenerTitel: false, verfuegbar: verfuegbar.has('zaehlerstaende'),
      render: () => <LiveZaehlerstaende staende={zaehlerstaende ?? []} />,
    },
    {
      // #263 — aus demselben Grund direkt hier: Werte, die eedc anzeigt, ohne
      // sie zu verrechnen.
      key: 'innengeraete', titel: 'Innengeräte', icon: Thermometer, eigenerTitel: false,
      verfuegbar: verfuegbar.has('innengeraete'),
      render: () => <LiveInnengeraete geraete={data.innengeraete ?? []} />,
    },
  ]

  // Element-Park-Doktrin (Gernot 2026-07-09): der Container ist KEINE eigene Anzeige —
  // sind ALLE verfügbaren Abschnitte geparkt, verschwindet die ganze „Auf einen Blick"-
  // Hülle (sonst bliebe ein leerer Kachel-Kopf stehen). Ohne ParkProvider (v3-IST) ist
  // `istGeparkt` immer false → nie versteckt, DOM unverändert.
  const sichtbareAbschnitte = abschnitte.filter((a) => a.verfuegbar)
  if (aufEinenBlickVollGeparkt({ data, wetter, prognose3Tage, zaehlerstaende }, park.istGeparkt)) {
    return null
  }

  return (
    <FokusKachel titel="Auf einen Blick" fokusId="live:auf-einen-blick" icon={LayoutGrid} zeigeTitel>
      <div className="space-y-4">
        {sichtbareAbschnitte.map((a) => (
          <Parkbar key={a.key} id={`live:${a.key}`} titel={a.titel}>
            <section>
              {!a.eigenerTitel && (
                <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                  <a.icon className="h-4 w-4 text-gray-400 dark:text-gray-500" />{a.titel}
                </h3>
              )}
              {a.render()}
            </section>
          </Parkbar>
        ))}
      </div>
    </FokusKachel>
  )
}
