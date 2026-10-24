/**
 * ModusChip — der Betriebsmodus eines Wärme/Klima-Geräts als Chip (SoT seit
 * P-433-2, Style-Guide Regel 0a: wiederkehrendes Element — Hub-Überblick, später
 * Leerlauf-Chip P-433-1 und Datenquellen S2).
 *
 * - **Form nach B17:** `rounded-full`, `text-xs`, neutrale Tönung
 *   (`bg-gray-50 … dark:bg-gray-700`), kein ALL-CAPS.
 * - **Farbe = Rolle der Funktion:** ein Punkt in der Chart-Farbe der Funktion
 *   (`funktionsFarbe`, dieselbe Quelle wie die Segmente der Wärme-Verteilung —
 *   eine Datenrolle, eine Farbe). Unbekannte/`aus`/`unbestimmt` ⇒ Grau.
 * - **Label aus dem Kanon:** der Aufrufer reicht `betriebsmodus_label` des
 *   Backends durch; der Client führt keine zweite Label-Tabelle.
 * - **«(passiv)»** hängt die EINE Funktion {@link modusMitPassiv} an — dieselbe,
 *   die die Kachel im Schaubild nutzt.
 */
import { funktionsFarbe } from '../../v4/waermeVerteilung'

/** Klartext eines Modus mit dem Zusatz «(passiv)» — eine Regel für Chip und Kachel. */
export function modusMitPassiv(label: string, passiv: boolean): string {
  return passiv ? `${label} (passiv)` : label
}

export interface ModusChipProps {
  /** Kanon-Wert (`heizen` · `warmwasser` · `kuehlen` · `lueften` · `entfeuchten` …). */
  modus: string
  /** Klartext aus dem Backend-Kanon (`betriebsmodus_label`). */
  label: string
  /** Kühlt das Gerät passiv (Stammdatum `kuehlung_art`)? Nur beim Kühlen sinnvoll. */
  passiv?: boolean
}

export default function ModusChip({ modus, label, passiv = false }: ModusChipProps) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs bg-gray-50 text-gray-700 dark:bg-gray-700 dark:text-gray-300 whitespace-nowrap"
      data-modus-chip={modus}
    >
      <span className="inline-block w-2 h-2 rounded-full" style={{ backgroundColor: funktionsFarbe(modus) }} data-modus-farbe />
      {modusMitPassiv(label, passiv)}
    </span>
  )
}
