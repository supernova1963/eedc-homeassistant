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
  /** Optionaler Tooltip je Option (z. B. Saison-Fenster-Zeitbereich). */
  title?: string
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
          title={o.title}
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

/**
 * SegmentMehrfach — dieselbe Pillen-Reihe, aber MEHRFACHauswahl (N-267).
 *
 * ⭐ **Warum hier und nicht daneben (Regel 0a Fall 2).** Für einen Wochentag-
 * Umschalter („an diesen Tagen gilt das Zeitfenster") gab es keine SoT: das
 * `SegmentControl` darüber ist per Vertrag Einfachauswahl (`value: string`,
 * `onChange(key)`), und `Checkbox` × 7 ist eine Liste, keine Leiste. Der erste
 * Entwurf baute die Pillen deshalb von Hand im Tarif-Formular — was
 * `check:roh-controls` zu Recht gemeldet hat.
 *
 * Statt einer zweiten Komponente irgendwo im Baum wohnt die Mehrfach-Variante
 * **in derselben Datei wie die Einfach-Variante** und teilt sich mit ihr Höhe
 * (`STEUER_H`), Umbruch-Regel (D18-1) und Aktiv-Stil. Was sich unterscheidet,
 * ist allein die Auswahl-Semantik — und die steht im Namen.
 *
 * `mindestensEine` (Vorgabe: an) verhindert die leere Auswahl: ein Zeitfenster
 * ohne Wochentag wäre kein Fenster, sondern ein unwirksamer Eintrag.
 */
export function SegmentMehrfach<K extends string>({
  optionen, werte, onToggle, ariaLabel, size = 'md', radius = 'lg',
  mindestensEine = true, className = '',
}: {
  optionen: readonly SegmentOption<K>[]
  /** Die aktiven Optionen. */
  werte: readonly K[]
  onToggle: (key: K) => void
  ariaLabel: string
  size?: 'sm' | 'md'
  radius?: 'md' | 'lg'
  /** Die letzte aktive Option lässt sich nicht abwählen. */
  mindestensEine?: boolean
  className?: string
}) {
  const pad = size === 'sm' ? 'px-2.5 text-xs' : 'px-3 text-sm'
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className={`inline-flex flex-wrap max-w-full ${radius === 'md' ? 'rounded-md' : 'rounded-lg'} border border-gray-200 dark:border-gray-700 overflow-hidden ${className}`}
    >
      {optionen.map((o) => {
        const an = werte.includes(o.key)
        const letzte = an && mindestensEine && werte.length === 1
        return (
          <button
            key={o.key}
            type="button"
            title={letzte ? 'Mindestens ein Eintrag muss gewählt bleiben' : o.title}
            aria-pressed={an}
            onClick={() => { if (!letzte) onToggle(o.key) }}
            className={`${pad} ${STEUER_H} inline-flex items-center font-medium transition-colors ${
              an
                ? 'bg-primary-600 text-white'
                : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50'
            } ${letzte ? 'cursor-default' : ''}`}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

export default SegmentControl
