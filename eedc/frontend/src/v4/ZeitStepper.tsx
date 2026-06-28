/**
 * ZeitStepper — generische, schwebende „Player"-Zeitauswahl der Cockpit-Zeitsichten
 * (mobil; L2b-Konsolidierung 2026-06-25). EINE SoT für Monat/Tag/Jahr statt drei
 * fast identischer Stepper: gemeinsame Hülle (sticky, halbtransparent + blur),
 * Pille (Player-Controls ⏮⏪◀ [Label ▾] ▶⏩⏭) und Dropdown-Liste leben hier; die
 * dünnen Adapter {@link MonatStepper}/{@link TagStepper}/{@link JahrStepper} liefern
 * nur noch die zeit-spezifische Navigation, Beschriftung und (Tag) das Datumsfeld.
 *
 * Unterschiede, die die Adapter kapseln: Zeit-Einheit (Monat (jahr,monat) · Tag
 * datum · Jahr jahr) · Button-Anzahl (Monat/Tag 3+3, Jahr 2+2) · Label-Format ·
 * Direktsprung (Tag: Date-Picker). Die überlaufende Liste bekommt den L1-
 * {@link ScrollSchatten}-Fade.
 */
import { useState, type ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { ChevronDown } from 'lucide-react'
import { ScrollSchatten } from '../components/ui/ScrollSchatten'

/** Ein Player-Schritt (Pfeil-Button). `go=null` → am Rand deaktiviert. */
export interface ZeitSchritt {
  icon: LucideIcon
  label: string
  go: (() => void) | null
}

/** Ein Listen-Eintrag der Dropdown-Auswahl (bereits in Anzeige-Reihenfolge). */
export interface ZeitStepperEintrag {
  key: string
  label: string
  /** Rechts-Wert, z. B. „123 kWh" oder „läuft"/„heute". */
  wert: string
  /** laufend/heute → grüner Wert (statt grau-tabular). */
  aktiv: boolean
  gewaehlt: boolean
  onClick: () => void
}

interface ZeitStepperProps {
  /** Schritte links von der Mitte (älter). */
  zurueck: ZeitSchritt[]
  /** Schritte rechts von der Mitte (neuer). */
  vor: ZeitSchritt[]
  /** Mittiger Titel (z. B. „Jun 2025" / „Mo 23. Juni 2025" / „2025"). */
  titel: string
  /** Badge in der Mitte („läuft"/„heute") oder null. */
  badge: string | null
  /** Dropdown-Liste (Anzeige-Reihenfolge, neueste zuerst). */
  eintraege: ZeitStepperEintrag[]
  /** Optionales Direktsprung-Element oben in der Liste (Tag: Date-Picker);
   *  bekommt eine `close`-Funktion zum Schließen der Liste nach Auswahl. */
  direktsprung?: (close: () => void) => ReactNode
  /** D10-2: im Fokus/Vollbild-Kopf wird der Stepper auf JEDER Breite gezeigt (kein
   *  `lg:hidden`) und sitzt nicht sticky — er ist dort die einzige Datums-Nav. */
  immerSichtbar?: boolean
}

const BTN_CLASS =
  'flex items-center justify-center h-9 w-8 shrink-0 rounded-md text-gray-600 dark:text-gray-300 ' +
  'hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors disabled:opacity-30 ' +
  'disabled:cursor-default disabled:hover:bg-transparent'

function StepBtn({ icon: Icon, label, go }: ZeitSchritt) {
  return (
    <button type="button" disabled={!go} onClick={() => go?.()} aria-label={label} title={label} className={BTN_CLASS}>
      <Icon className="h-4 w-4" />
    </button>
  )
}

export function ZeitStepper({ zurueck, vor, titel, badge, eintraege, direktsprung, immerSichtbar = false }: ZeitStepperProps) {
  const [offen, setOffen] = useState(false)

  // D7-3 (detLAN R7): KEIN Voll-Bleed (`-mx-3`) mehr → der Streifen bleibt auf
  // Inhaltsbreite (12px-Gutter der `p-3`-Wurzel). Der mobile Overlay-Scrollbalken
  // schwebt damit im rechten Gutter statt über der Nav. `scrollbar-gutter` (mobil,
  // No-Op bei Overlay-Scrollbalken) wird dadurch entbehrlich.
  return (
    <div className={immerSichtbar
      ? 'mb-3'
      : 'lg:hidden sticky top-0 z-20 pt-1 pb-2 mb-3 bg-gray-50/80 dark:bg-gray-900/80 backdrop-blur-sm'}>
      <div className="flex items-center gap-0.5 max-w-md mx-auto rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-1 py-1 shadow-sm">
        {zurueck.map((s, i) => <StepBtn key={`z${i}`} {...s} />)}
        <button
          type="button"
          onClick={() => setOffen((o) => !o)}
          aria-expanded={offen}
          className="flex-1 flex items-center justify-center gap-1.5 h-9 min-w-0 rounded-md text-sm font-semibold text-gray-900 dark:text-white hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors"
        >
          <span className="truncate">{titel}</span>
          {badge && (
            <span className="text-[10px] leading-none px-1 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">{badge}</span>
          )}
          <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${offen ? 'rotate-180' : ''}`} />
        </button>
        {vor.map((s, i) => <StepBtn key={`v${i}`} {...s} />)}
      </div>

      {offen && (
        <div className="mt-1 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg overflow-hidden">
          {direktsprung && (
            <div className="px-3 py-2 border-b border-gray-100 dark:border-gray-700/50">
              {direktsprung(() => setOffen(false))}
            </div>
          )}
          <ScrollSchatten achse="vertikal" className="max-h-72" fadeFrom="from-white dark:from-gray-800">
            <div className="divide-y divide-gray-100 dark:divide-gray-700/50">
              {eintraege.map((e) => (
                <button
                  key={e.key}
                  type="button"
                  onClick={() => { e.onClick(); setOffen(false) }}
                  className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-sm transition-colors ${
                    e.gewaehlt
                      ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 font-semibold'
                      : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/40'
                  }`}
                >
                  <span>{e.label}</span>
                  <span className={`text-xs ${e.aktiv ? 'text-emerald-500 dark:text-emerald-400' : 'text-gray-400 dark:text-gray-500 tabular-nums'}`}>
                    {e.wert}
                  </span>
                </button>
              ))}
            </div>
          </ScrollSchatten>
        </div>
      )}
    </div>
  )
}
