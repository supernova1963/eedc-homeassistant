/**
 * monatParkScope — der `localStorage`-Scope des Element-Parks von Cockpit → Monat.
 *
 * **Warum eine eigene Datei für eine Konstante.** Seit dem Monatsbericht (#395
 * Punkt 4) hat der Park-Zustand dieser Sicht einen **zweiten** Leser: der
 * Berichts-Dialog schickt die geparkten IDs beim Erzeugen mit, damit der
 * Bericht so aussieht wie die Ansicht des Anwenders. Der Dialog hängt aber
 * nicht im Render-Baum der Monatssicht — er würde beim Import von
 * `CockpitMonatV4` die ganze Sicht ins Bündel ziehen, nur um eine Zeichenkette
 * zu lesen. Dieselbe Begründung wie bei `bilanzParkIds.ts`.
 *
 * ⛔ **Nicht abschreiben, importieren.** Ein zweites `'v4-cockpit-monat'` im
 * Dialog wäre still falsch, sobald der Schlüssel sich ändert: Der Bericht
 * bekäme dann eine leere Liste und wäre vollständig — ohne Fehler, ohne
 * Meldung, nur mit einem anderen Ergebnis als versprochen.
 */

/** Park-Scope (Element-Ebene) der Monats-Sicht. Prefix `eedc-park:` ergänzt
 *  {@link ParkProvider} selbst; hier steht nur der Sicht-Teil. */
export const MONAT_PARK_KEY = 'v4-cockpit-monat'
