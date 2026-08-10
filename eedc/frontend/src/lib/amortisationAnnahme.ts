/**
 * Die Annahme hinter einer Amortisations**dauer** — Client-Pendant.
 *
 * SoT der Formulierung ist das Backend
 * (`core/berechnungen/kapitalrechnung.py::annahme_dauer_text`); wo eine Dauer
 * aus einer Response kommt, wird der dort gebildete Text **mitgeliefert** und
 * nur angezeigt (`ROIDashboardResponse.amortisation_annahme` und je Zeile).
 *
 * Diese Datei trägt den Fall, für den es keine Backend-Zahl gibt: der
 * Komponenten-Hub der Wallbox bildet seine Dauer selbst aus
 * `anschaffungskosten_gesamt ÷ Jahres-Ersparnis` — dort gibt es keinen
 * Betriebskosten-Abzug und damit **immer** Modell A (Konzept §5).
 *
 * ⚠ Wer hier einen zweiten Satz erfindet, statt den gelieferten anzuzeigen,
 * baut die Drift, die Bauschritt 6 gerade beseitigt: dieselbe Zahl mit zwei
 * verschiedenen Voraussetzungen daneben.
 *
 * Konzept: `docs/KONZEPT-WIRTSCHAFTLICHKEITSRECHNUNG.md` §5 + §8/6.
 */

/**
 * Modell A („es geht nie wieder etwas kaputt") — wortgleich mit dem
 * Backend-SoT. Gilt nur für Dauern, in deren Rechnung **kein**
 * `betriebskosten_jahr` steckt.
 */
export const AMORTISATION_ANNAHME_MODELL_A = 'ohne künftige Instandhaltung'

/** Vorangestelltes Label — eine Schreibweise für alle Dauer-Anzeigen. */
export const AMORTISATION_ANNAHME_LABEL = 'Annahme'

/**
 * Fertige Zeile („Annahme: ohne künftige Instandhaltung").
 *
 * @param annahme Der vom Backend gelieferte Text; fehlt er, entsteht **keine**
 *   Zeile — ein Platzhalter würde eine Voraussetzung behaupten, die niemand
 *   geprüft hat.
 */
export function amortisationAnnahmeZeile(annahme?: string | null): string | null {
  if (!annahme) return null
  return `${AMORTISATION_ANNAHME_LABEL}: ${annahme}`
}
