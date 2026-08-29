/**
 * Die Annahme hinter einer Amortisations**dauer** — Client-Pendant.
 *
 * SoT der Formulierung ist das Backend
 * (`core/berechnungen/kapitalrechnung.py::annahme_dauer_text`); wo eine Dauer
 * aus einer Response kommt, wird der dort gebildete Text **mitgeliefert** und
 * nur angezeigt (`ROIDashboardResponse.amortisation_annahme` und je Zeile).
 *
 * ⛔ **Es gibt keinen Fall mehr, in dem der Client den Satz selbst wählt.**
 * Bis N-230 (2026-08-29) trug diese Datei eine Konstante
 * `AMORTISATION_ANNAHME_MODELL_A` für die eine Ausnahme: der Wallbox-Hub
 * bildete seine Dauer selbst aus `anschaffungskosten_gesamt ÷ Ersparnis`, wo
 * per Konstruktion kein Betriebskosten-Abzug steckte. Seit die Dauer aus dem
 * Kapitalrechnungs-SoT kommt, liefert die Antwort ihren Annahme-Text mit —
 * die Konstante hatte **null** Konsumenten und ist entfernt.
 *
 * ⚠ Wer hier einen zweiten Satz erfindet, statt den gelieferten anzuzeigen,
 * baut die Drift, die Bauschritt 6 gerade beseitigt: dieselbe Zahl mit zwei
 * verschiedenen Voraussetzungen daneben.
 *
 * Konzept: `docs/KONZEPT-WIRTSCHAFTLICHKEITSRECHNUNG.md` §5 + §8/6.
 */

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
