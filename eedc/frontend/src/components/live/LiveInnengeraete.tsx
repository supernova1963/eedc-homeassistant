/**
 * LiveInnengeraete — die Innengeräte einer Split-Klimaanlage (#263).
 *
 * Gebaut nach dem Muster von `LiveZaehlerstaende` daneben, und das ist kein
 * Zufall: **ein Nicht-Bilanz-Wert je Gerät, reine Anzeige, geht in keine
 * Berechnung ein.** Die Leistung eines Innengeräts ist eine *Teilmenge* der
 * Geräteleistung, die als Komponente ohnehin schon zählt — sie hier zu
 * addieren wäre eine Doppelzählung.
 *
 * Gibt `null` zurück, wenn kein Innengerät einen Wert liefert. Dann fehlt der
 * Abschnitt ganz, statt leere Zeilen zu stellen.
 */
import { fmtZahl } from '../../lib'
import type { LiveInnengeraet } from '../../api/liveDashboard'

export default function LiveInnengeraete({ geraete }: { geraete: LiveInnengeraet[] }) {
  const mitWert = geraete.filter(
    (g) => g.leistung_w != null || g.ist_temperatur_c != null || g.soll_temperatur_c != null,
  )
  if (mitWert.length === 0) return null

  return (
    <div className="flex flex-wrap gap-2">
      {mitWert.map((g) => (
        <div
          key={`${g.investition_id}-${g.innengeraet_id}`}
          className="flex-1 min-w-[10rem] bg-gray-50 dark:bg-gray-800/40 rounded-lg px-3 py-1.5"
          title={g.bezeichnung}
        >
          <div className="text-xs text-gray-500 dark:text-gray-400 truncate">{g.bezeichnung}</div>
          {/* Die Raumtemperatur steht oben, weil sie die Frage beantwortet,
              wegen der jemand auf ein Innengerät schaut. Fehlt sie, rückt die
              Leistung nach — es steht nie eine 0 für „nicht gemessen"
              (ADR-002/P4). */}
          {g.ist_temperatur_c != null ? (
            <div className="text-base font-bold text-gray-700 dark:text-gray-200">
              {fmtZahl(g.ist_temperatur_c, 1)}
              <span className="text-xs font-normal ml-0.5">°C</span>
              {g.soll_temperatur_c != null && (
                <span className="text-xs font-normal text-gray-500 dark:text-gray-400 ml-1">
                  (Soll {fmtZahl(g.soll_temperatur_c, 1)} °C)
                </span>
              )}
            </div>
          ) : g.soll_temperatur_c != null && (
            <div className="text-base font-bold text-gray-700 dark:text-gray-200">
              Soll {fmtZahl(g.soll_temperatur_c, 1)}
              <span className="text-xs font-normal ml-0.5">°C</span>
            </div>
          )}
          {g.leistung_w != null && (
            <div className="text-xs text-gray-500 dark:text-gray-400">
              {fmtZahl(g.leistung_w, 0)} W
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
