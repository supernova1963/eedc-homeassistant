/**
 * DatenquellenTopicListe — die MQTT-Topics dieser Anlage zum Nachschlagen.
 *
 * Zweck (Gernot 2026-08-20): Wer seine Werte aus ioBroker, FHEM, evcc oder einem
 * eigenen Skript nach eedc schicken will, braucht die Topics **am Stück** und zum
 * Kopieren — nicht verstreut unter den einzelnen Feldern und nicht erst, nachdem
 * er auf „MQTT-Inbound" geklickt hat.
 *
 * Zwei Entscheide dazu, beide von Gernot:
 *  - **Nur vorhandene Geräte.** „Nur die sind wirksam" — die Liste zeigt genau die
 *    Felder, die die Zuordnungs-Fläche ohnehin führt, kein Katalog aller denkbaren.
 *  - **Sie gehört zu *Datenquellen***, nicht zu *Integration*.
 *
 * Datenquelle ist bewusst `DatenquelleGruppe[]` — dieselben Daten, die die Fläche
 * schon geladen hat (`standard_topic` steckt in jedem Feld). Kein zweiter Request,
 * damit Liste und Zuordnung nicht auseinanderlaufen können. (Der ungenutzte
 * Endpunkt `GET /live/mqtt/topics` bleibt davon unberührt.)
 */
import { Copy, Check } from 'lucide-react'
import { Button } from '../ui'
import { useCopyFeedback } from '../../hooks'
import type { DatenquelleGruppe, DatenquelleFeld } from '../../api/datenquellen'

interface Props {
  gruppen: DatenquelleGruppe[]
}

/** Felder ohne Standard-Topic (Preis-Felder sind `nur_ha`) gehören nicht in die Liste. */
function mitTopic(felder: DatenquelleFeld[]): DatenquelleFeld[] {
  return felder.filter((f) => !f.nur_ha && !!f.standard_topic)
}

export default function DatenquellenTopicListe({ gruppen }: Props) {
  const { istKopiert, kopiere } = useCopyFeedback()

  const gefuellt = gruppen
    .map((g) => ({ ...g, felder: mitTopic(g.felder) }))
    .filter((g) => g.felder.length > 0)

  const alle = gefuellt.flatMap((g) => g.felder.map((f) => f.standard_topic))

  if (alle.length === 0) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Für diese Anlage gibt es keine MQTT-Topics — es sind keine Geräte angelegt.
      </p>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-sm text-gray-600 dark:text-gray-300 max-w-3xl">
          Auf diese Topics kannst du Werte schicken — aus ioBroker, FHEM, evcc oder einem
          eigenen Skript. eedc holt dort nichts ab, es hört zu: Sobald auf einem Topic ein
          Wert ankommt, wird das zugehörige Feld von selbst auf <em>MQTT-Inbound</em>
          gestellt. Ein Wert je Nachricht, als Zahl.
        </p>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => kopiere(alle.join('\n'), 'alle')}
          title="Alle Topics als Liste kopieren"
        >
          {istKopiert('alle')
            ? <><Check size={16} className="mr-1.5" /> Kopiert</>
            : <><Copy size={16} className="mr-1.5 max-sm:hidden" /> Alle kopieren</>}
        </Button>
      </div>

      {gefuellt.map((g) => (
        <div key={g.id}>
          <div className="pt-1 pb-0.5 text-xs font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500">
            {g.titel}
          </div>
          <div className="divide-y divide-gray-100 dark:divide-gray-800">
            {g.felder.map((f) => (
              <div key={f.id} className="flex items-center gap-3 py-1.5">
                <div className="min-w-0 flex-1">
                  <code className="block truncate text-xs text-gray-700 dark:text-gray-200">
                    {f.standard_topic}
                  </code>
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    {f.label}{f.einheit ? ` (${f.einheit})` : ''}
                  </span>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => kopiere(f.standard_topic, f.id)}
                  title={`Topic für „${f.label}" kopieren`}
                  aria-label={`Topic für ${f.label} kopieren`}
                >
                  {istKopiert(f.id) ? <Check size={16} /> : <Copy size={16} />}
                </Button>
              </div>
            ))}
          </div>
        </div>
      ))}

      <p className="text-xs text-gray-500 dark:text-gray-400">
        Der Namensteil hinter der Anlagennummer ist optional —{' '}
        <code>eedc/1/live/…</code> wirkt genauso wie <code>eedc/1_Meine-Anlage/live/…</code>.
        Ein eingerichteter Geräte-Connector nutzt intern denselben Weg und schreibt
        die kurze Form.
      </p>
    </div>
  )
}
