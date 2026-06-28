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
import { Calendar, Sunrise, Sun, Battery, Thermometer, LayoutGrid } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { FokusKachel } from '../blocks'
import { Parkbar } from '../park'
import LiveHeuteKacheln from './LiveHeuteKacheln'
import SunProgressBar from './SunProgressBar'
import SolarAussicht3Tage from './SolarAussicht3Tage'
import LiveSocBalken from './LiveSocBalken'
import LiveTemperaturen from './LiveTemperaturen'
import type { LiveDashboardResponse, LiveWetterResponse } from '../../api/liveDashboard'
import type { SolarPrognoseTag } from '../../api/wetter'

interface Abschnitt {
  key: string
  titel: string
  icon: LucideIcon
  /** Bringt die Sub-Komponente ihre eigene Überschrift mit? Sonst ergänzen wir eine. */
  eigenerTitel: boolean
  verfuegbar: boolean
  render: () => ReactNode
}

export default function LiveAufEinenBlick({ data, wetter, prognose3Tage }: {
  data: LiveDashboardResponse
  wetter: LiveWetterResponse | null
  prognose3Tage: SolarPrognoseTag[] | null
}) {
  const hatSonne = !!(wetter?.sunrise && wetter?.sunset)
  const hatAussicht = !!(prognose3Tage && prognose3Tage.length > 0)
  const hatSoc = !!data.gauges?.some((g) => g.key.startsWith('soc_'))
  const hatTemp = !!(wetter?.aktuell?.temperatur_c != null || data.warmwasser_temperatur_c != null)

  const abschnitte: Abschnitt[] = [
    {
      key: 'heute', titel: 'Heute', icon: Calendar, eigenerTitel: true, verfuegbar: true,
      render: () => <LiveHeuteKacheln data={data} />,
    },
    {
      key: 'sonnenstand', titel: 'Sonnenstand', icon: Sunrise, eigenerTitel: false, verfuegbar: hatSonne,
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
      key: 'solar-aussicht', titel: 'Solar-Aussicht', icon: Sun, eigenerTitel: true, verfuegbar: hatAussicht,
      render: () => <SolarAussicht3Tage prognose3Tage={prognose3Tage!} wetter={wetter} heutePvKwh={data.heute_pv_kwh} />,
    },
    {
      key: 'ladezustand', titel: 'Ladezustand', icon: Battery, eigenerTitel: true, verfuegbar: hatSoc,
      render: () => <LiveSocBalken gauges={data.gauges} />,
    },
    {
      key: 'temperaturen', titel: 'Temperaturen', icon: Thermometer, eigenerTitel: false, verfuegbar: hatTemp,
      render: () => (
        <LiveTemperaturen
          aussenC={wetter?.aktuell?.temperatur_c}
          tempMinC={wetter?.temperatur_min_c}
          tempMaxC={wetter?.temperatur_max_c}
          warmwasserC={data.warmwasser_temperatur_c}
        />
      ),
    },
  ]

  return (
    <FokusKachel titel="Auf einen Blick" icon={LayoutGrid} zeigeTitel>
      <div className="space-y-4">
        {abschnitte.filter((a) => a.verfuegbar).map((a) => (
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
