import { STEUER_H } from '../../lib/komponentenStyle'

/**
 * SegmentControl — DER Segment-Umschalter-SoT (Style-Guide B15, R3b S4 2026-07-05).
 *
 * Löst 6 handgebaute Segment-/Pillen-Gruppen mit 5 driftenden Höhen ab (Finanzen
 * Monat/Jahr, Werkbank Aus/Vorjahr, Jahr-/Tagesverlauf Erzeugung/Verbrauch,
 * Komponenten-Vergleich Diagramm/Tabelle, Aussicht-Horizont, Aussicht Heute/Morgen).
 * Kanon: Höhe = `STEUER_H` (32-px-Toolbar-Klasse), Aktiv-Stil = gefülltes
 * `bg-primary-600 text-white` (Toolbar-Familie; der Primary-**Tint** bleibt
 * Navigations-Tabs vorbehalten, B3 „Aktiver Reiter"). `aria-pressed` je Option.
 *
 * `value`, das keiner Option entspricht, ist erlaubt (alle inaktiv) — z. B.
 * Heute/Morgen-Shortcuts, wenn der DatumPicker auf +2..+14 steht.
 *
 * D18-1 (detlan #210, Regel im SoT): Passen die Optionen nicht in die verfügbare
 * Breite, BRECHEN sie um (`flex-wrap` + `max-w-full`) — nie hart abschneiden
 * (vorher: `inline-flex … overflow-hidden` ohne Wrap ⇒ letzte Pille mobil
 * gekappt, z. B. Vergleich-Presets in Tages-/JahrVerlaufChart). Umbruch statt
 * horizontalem Scrollen: bei einem Umschalter müssen ALLE Optionen sichtbar
 * sein. Der Fix lebt in der Zentrale — jeder Aufrufer erbt ihn.
 */
interface SegmentOption<K extends string> {
  key: K
  label: string
}

export function SegmentControl<K extends string>({
  optionen, value, onChange, ariaLabel, size = 'md', radius = 'lg', className = '',
}: {
  optionen: readonly SegmentOption<K>[]
  /** Aktive Option — darf auch KEINER Option entsprechen (alle inaktiv). */
  value: string
  onChange: (key: K) => void
  ariaLabel: string
  /** sm = text-xs px-2.5 (kompakte Leisten) · md = text-sm px-3. Höhe immer STEUER_H. */
  size?: 'sm' | 'md'
  /** rounded-md für Zeit-Nav-Kompakt-Kontexte (S10), sonst rounded-lg. */
  radius?: 'md' | 'lg'
  className?: string
}) {
  const pad = size === 'sm' ? 'px-2.5 text-xs' : 'px-3 text-sm'
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={`inline-flex flex-wrap max-w-full ${radius === 'md' ? 'rounded-md' : 'rounded-lg'} border border-gray-200 dark:border-gray-700 overflow-hidden ${className}`}
    >
      {optionen.map((o) => (
        <button
          key={o.key}
          type="button"
          aria-pressed={value === o.key}
          onClick={() => onChange(o.key)}
          className={`${pad} ${STEUER_H} inline-flex items-center font-medium transition-colors ${
            value === o.key
              ? 'bg-primary-600 text-white'
              : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export default SegmentControl
