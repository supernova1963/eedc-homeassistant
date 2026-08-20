/**
 * ZaehlerVerlaufChart — der Zählerstand über die Zeit (#377).
 *
 * **Eine Linie, keine Balken** — und das ist keine Geschmacksfrage: Ein
 * Zählerstand ist eine **Bestands**größe. Balken lesen sich als Mengen je
 * Zeitabschnitt und laden dazu ein, sie zu addieren; eine monoton steigende
 * Linie sagt, was ein Zähler tut. Aus demselben Grund beginnt die Y-Achse
 * **nicht bei null**: der interessante Bereich ist die Bewegung, nicht der
 * Abstand zum Nullpunkt (ein Gaszähler bei 12.345 zeigt sonst eine flache
 * Gerade).
 *
 * **Je Zähler eine eigene Linie mit eigener Achse gibt es bewusst nicht.**
 * Verschiedene Einheiten auf einer Achse sind die Verwechslung, vor der der
 * `soc_je_speicher`-Kommentar im Backend warnt — deshalb rendert diese
 * Komponente **ein Diagramm je Gerät** untereinander statt eines gemeinsamen.
 */
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { xAchse, yAchse, achsenEinheit, achsenTick, ACHSEN_MARGIN_TOP } from '../../lib'
import { KOMPONENTEN_FARBEN } from '../../lib/colors'
import { useSchmaleAchse } from '../../hooks'
import { eedcTooltipProps } from '../ui'
import type { ZaehlerStand } from '../../api/zaehlerstaende'

function formatiereZeit(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })
}

export default function ZaehlerVerlaufChart({ staende }: { staende: ZaehlerStand[] }) {
  const schmal = useSchmaleAchse()
  const mitVerlauf = staende.filter((z) => z.verlauf.length > 1)
  if (mitVerlauf.length === 0) return null

  return (
    <div className="space-y-4">
      {mitVerlauf.map((z) => {
        const rows = z.verlauf.map((p) => ({
          name: formatiereZeit(p.zeitpunkt),
          stand: p.stand,
        }))
        return (
          <div key={z.investition_id}>
            <div className="text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">
              {z.name} <span className="font-normal text-gray-400">({z.einheit})</span>
            </div>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={rows} margin={{ top: ACHSEN_MARGIN_TOP, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="name" {...xAchse(schmal)} interval="preserveStartEnd" /* achsen-allow: Zeit-/Kategorie-Achse */ />
                  <YAxis
                    {...yAchse(schmal, 60)}
                    /* Bestandsgröße: der Ausschnitt zeigt die Bewegung, nicht den
                       Abstand zur Null. `domain` bewusst nicht auf 0 verankert. */
                    domain={['dataMin', 'dataMax']}
                    tickFormatter={achsenTick}
                    label={achsenEinheit(z.einheit)}
                  />
                  <Tooltip {...eedcTooltipProps({ unit: z.einheit, decimals: 1 })} />
                  <Line
                    type="monotone"
                    dataKey="stand"
                    name="Zählerstand"
                    /* Farb-SoT: die Komponenten-Identität von `sonstiges` (Grau). Bewusst
                       KEINE Rollenfarbe aus COLORS — die stehen für Rollen in der
                       Energiebilanz, an der ein Zählerstand nicht teilnimmt. */
                    stroke={KOMPONENTEN_FARBEN['sonstiges'].hex}
                    dot={false}
                    strokeWidth={2}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )
      })}
    </div>
  )
}
