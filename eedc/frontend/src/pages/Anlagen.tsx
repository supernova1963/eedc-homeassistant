/**
 * Anlagen (IST/V3) — dünner Komposer über die geteilten `AnlagenTeile`.
 *
 * Der gesamte Inhalt (Tabelle, Anlegen-/Bearbeiten-/Lösch-Modals, Export,
 * Dokumente-Dialog) lebt in {@link ./AnlagenTeile} als EINE Code-Wahrheit —
 * dieselben Teile speisen den IA-V4-Stammdaten-Block „Anlage".
 * #218: Überschrift „Anlagen" entfernt — der Sub-Tab benennt den Bereich.
 */
import { AnlagenVerwaltung } from './AnlagenTeile'

export default function Anlagen() {
  return <AnlagenVerwaltung />
}
