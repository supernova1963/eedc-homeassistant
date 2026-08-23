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
 *
 * ⚠ **Die Achse zeigt, was das Fenster unterscheidet — nicht mehr und nicht
 * weniger** (dietmar1968, simon42 T89667 #187, 23.08.2026). Bis dahin
 * formatierte die Komponente in *allen* Sichten `TT.MM.`, weil sie den Zeitraum
 * gar nicht kannte: Sie nahm ein einziges Prop. In der **Tages**ansicht trug
 * damit jeder der stündlichen Punkte dasselbe Datum — vierzehn Ticks, eine
 * Aussage, nämlich keine. Die Uhrzeit war die ganze Zeit da
 * (`VerlaufPunkt.zeitpunkt` ist ein voller Zeitstempel) und wurde beim
 * Beschriften weggeworfen.
 *
 * **Deshalb trägt der Datenpunkt jetzt den ISO-Zeitstempel selbst** und nicht
 * mehr ein vorgebackenes Label: Die **Achse** kürzt ihn über `tickFormatter`
 * auf das, was im Fenster variiert, der **Tooltip** zeigt ihn über
 * `labelFormatter` vollständig. Das ist der Grund, warum ein einzelner Punkt
 * auch dort eindeutig bleibt, wo mehrere auf denselben Tick fallen — im
 * Monats- und Jahresfenster liegen bei stündlicher Messung 24 Punkte auf
 * demselben Tag.
 */
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import {
  xAchse, yAchse, achsenEinheit, achsenTick, ACHSEN_MARGIN_TOP,
  formatDatumZeit, formatUhrzeit,
} from '../../lib'
import { KOMPONENTEN_FARBEN } from '../../lib/colors'
import { useSchmaleAchse } from '../../hooks'
import { eedcTooltipProps } from '../ui'
import type { ZaehlerStand, ZaehlerZeitraum } from '../../api/zaehlerstaende'

/**
 * Achsenbeschriftung je Fenster — jede zeigt genau die Ebene, auf der sich die
 * Punkte im jeweiligen Zeitraum unterscheiden.
 *
 * `monat` ist **absichtlich unverändert** gegenüber der Fassung vor dem Fix
 * (`'23.08.'`): Dort war die Beschriftung nie falsch, und eine vertraute
 * Anzeige wird nur geändert, wo es nötig ist.
 */
function achsenLabel(iso: string, zeitraum: ZaehlerZeitraum): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  switch (zeitraum) {
    case 'tag':
      return formatUhrzeit(iso)
    case 'jahr':
      return d.toLocaleString('de-DE', { month: 'short' })
    case 'gesamt':
      return d.toLocaleString('de-DE', { month: 'short', year: '2-digit' })
    default:
      return d.toLocaleString('de-DE', { day: '2-digit', month: '2-digit' })
  }
}

export default function ZaehlerVerlaufChart(
  { staende, zeitraum }: { staende: ZaehlerStand[]; zeitraum: ZaehlerZeitraum },
) {
  const schmal = useSchmaleAchse()
  const mitVerlauf = staende.filter((z) => z.verlauf.length > 1)
  if (mitVerlauf.length === 0) return null

  return (
    <div className="space-y-4">
      {mitVerlauf.map((z) => {
        // `name` trägt den ISO-Zeitstempel selbst — Achse und Tooltip
        // formatieren ihn verschieden weit (s. Kopfkommentar).
        const rows = z.verlauf.map((p) => ({
          name: p.zeitpunkt,
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
                  <XAxis
                    dataKey="name"
                    {...xAchse(schmal)}
                    interval="preserveStartEnd"
                    tickFormatter={(v: string) => achsenLabel(v, zeitraum)}
                    /* achsen-allow: Zeit-/Kategorie-Achse */
                  />
                  <YAxis
                    {...yAchse(schmal, 60)}
                    /* Bestandsgröße: der Ausschnitt zeigt die Bewegung, nicht den
                       Abstand zur Null. `domain` bewusst nicht auf 0 verankert. */
                    domain={['dataMin', 'dataMax']}
                    tickFormatter={achsenTick}
                    label={achsenEinheit(z.einheit)}
                  />
                  <Tooltip
                    {...eedcTooltipProps({
                      unit: z.einheit,
                      decimals: 1,
                      // Der Punkt trägt den vollen Zeitstempel — im Tooltip
                      // steht er ungekürzt, damit ein einzelner Messwert auch
                      // dann eindeutig ist, wenn mehrere auf denselben
                      // Achsen-Tick fallen.
                      labelFormatter: (v) => formatDatumZeit(String(v)),
                    })}
                  />
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
