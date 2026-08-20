/**
 * LiveZaehlerstaende — die Zählerstände im Abschnitt *Auf einen Blick* (#377).
 *
 * Gebaut nach dem Muster von `LiveTemperaturen` daneben: **ein Nicht-Energie-Wert
 * je Gerät, reine Anzeige, geht in keine Berechnung ein.** Das ist kein
 * Zufall — `warmwasser_temperatur_c` ist der Präzedenzfall, an dem sich zeigt,
 * wie eedc einen Messwert führt, der nichts zur Bilanz beiträgt.
 *
 * Gezeigt werden zwei Zahlen je Zähler: der **aktuelle Stand** (die Zahl, die
 * auf dem Zähler steht) und die **Veränderung heute**. Gibt `null` zurück, wenn
 * es keinen Zähler gibt — dann fehlt der Abschnitt ganz, statt leer dazustehen.
 */
import { fmtZahl } from '../../lib'
import { ZAEHLER_ART_LABELS } from '../../lib/constants'
import type { ZaehlerStand } from '../../api/zaehlerstaende'

export default function LiveZaehlerstaende({ staende }: { staende: ZaehlerStand[] }) {
  const mitWert = staende.filter((z) => z.stand_ende != null)
  if (mitWert.length === 0) return null

  return (
    <div className="flex flex-wrap gap-2">
      {mitWert.map((z) => {
        const artLabel = ZAEHLER_ART_LABELS[z.art] ?? z.art
        return (
          <div
            key={z.investition_id}
            className="flex-1 min-w-[10rem] bg-gray-50 dark:bg-gray-800/40 rounded-lg px-3 py-1.5"
            title={`${artLabel} · ${z.name}`}
          >
            <div className="text-xs text-gray-500 dark:text-gray-400 truncate">{z.name}</div>
            <div className="text-base font-bold text-gray-700 dark:text-gray-200">
              {fmtZahl(z.stand_ende as number, 1)}
              <span className="text-xs font-normal ml-0.5">{z.einheit}</span>
            </div>
            {/* Die Veränderung ist die EINZIGE Rechnung auf einem Zählerstand.
                Fehlt ein Stand, steht hier nichts — nicht „0" (ADR-002/P4). */}
            {z.differenz != null && (
              <div className="text-xs text-gray-500 dark:text-gray-400">
                heute {z.differenz >= 0 ? '+' : ''}
                {fmtZahl(z.differenz, 1)} {z.einheit}
                {!z.anfang_vollstaendig && (
                  <span
                    className="ml-1"
                    title="Die Aufzeichnung hat erst im Laufe des Tages begonnen — der Wert deckt nicht den ganzen Tag ab."
                  >
                    (Teil)
                  </span>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
