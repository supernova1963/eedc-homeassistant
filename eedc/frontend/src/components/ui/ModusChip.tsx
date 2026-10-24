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
 * - **«· Leerlauf»** (P-433-1, Konzept #433 E6): die gemessene Ruhe aus
 *   `hvac_action: idle` steht NEBEN dem Kanon-Wert; der Chip wird gedämpft. Den
 *   Text baut die EINE Funktion {@link modusKlartext} — dieselbe für Chip,
 *   Kachel-Tooltips (Energiefluss, Überblick) und die Gruppen-Liste.
 */
import type { LiveKomponente } from '../../api/liveDashboard'
import { funktionsFarbe } from '../../lib/funktionsFarben'

/** Klartext eines Modus mit dem Zusatz «(passiv)» — eine Regel für Chip und Kachel. */
export function modusMitPassiv(label: string, passiv: boolean): string {
  return passiv ? `${label} (passiv)` : label
}

/**
 * Der Modus im Klartext mit der gemessenen Aktion — «Heizen · Leerlauf», «Kühlen (passiv) · Leerlauf»;
 * ohne Aktion wie bisher. `null` ohne Klartext (kein Modus, `unbestimmt`). Beide Texte kommen vom
 * Backend-Kanon (`betriebsmodus_label`, `betriebsmodus_aktion_label`); hier wird nur gefügt.
 */
export function modusKlartext(
  k: Pick<LiveKomponente, 'betriebsmodus_label' | 'betriebsmodus_aktion_label'>,
  passiv = false,
): string | null {
  if (!k.betriebsmodus_label) return null
  const basis = modusMitPassiv(k.betriebsmodus_label, passiv)
  return k.betriebsmodus_aktion_label ? `${basis} · ${k.betriebsmodus_aktion_label}` : basis
}

export interface ModusChipProps {
  /** Kanon-Wert (`heizen` · `warmwasser` · `kuehlen` · `lueften` · `entfeuchten` …). */
  modus: string
  /** Klartext aus dem Backend-Kanon (`betriebsmodus_label`). */
  label: string
  /** Kühlt das Gerät passiv (Stammdatum `kuehlung_art`)? Nur beim Kühlen sinnvoll. */
  passiv?: boolean
  /** Klartext der gemessenen Aktion (`betriebsmodus_aktion_label`, heute «Leerlauf») — gesetzt ⇒ gedämpft. */
  aktion?: string | null
}

export default function ModusChip({ modus, label, passiv = false, aktion = null }: ModusChipProps) {
  const gedaempft = aktion != null
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs bg-gray-50 dark:bg-gray-700 whitespace-nowrap ${
        gedaempft ? 'text-gray-500 dark:text-gray-400' : 'text-gray-700 dark:text-gray-300'}`}
      data-modus-chip={modus}
      data-modus-aktion={gedaempft ? '' : undefined}
    >
      <span
        className={`inline-block w-2 h-2 rounded-full${gedaempft ? ' opacity-50' : ''}`}
        style={{ backgroundColor: funktionsFarbe(modus) }}
        data-modus-farbe
      />
      {modusKlartext({ betriebsmodus_label: label, betriebsmodus_aktion_label: aktion }, passiv)}
    </span>
  )
}
