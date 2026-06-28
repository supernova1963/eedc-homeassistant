/**
 * KPICard — Single Source of Truth für Kennzahl-Kacheln (Style-Guide B9/B1, #258).
 *
 * EINZIGE KPICard-Definition der App. Drei Größen, ein Farb-Enum (`KomponentenColor`
 * aus `lib/komponentenStyle` → `COLOR_CLASSES`, Werte aus `lib/colors.ts`):
 *
 *   md  (Default)  Standard-Kachel mit farbiger Icon-Box (Cockpit/Auswertung/Dashboards)
 *   sm             Kompaktform ohne Icon-Box — Wert trägt die Farbe (Energieprofil-Streifen)
 *   lg             Prominente Kachel (Hero/Featured)
 *
 * Konventionen (B1 #258): Einheit immer gedämpft hinter dem Wert, Icon-Position
 * konsistent rechts (boxed) bzw. inline links vor dem Label (sm). EINZEILIG: die
 * ZAHL ist unantastbar (`flex-shrink-0 whitespace-nowrap` — nie gekürzt); reicht
 * der Platz nicht, kürzt NUR die Einheit mit `…` (`min-w-0 truncate`), kein Umbruch
 * (#243 Gernot). Die Grid-Mindestbreite (`auto-fit minmax`, KpiStrip = 248 px) ist
 * so gewählt, dass Zahl (bis ~7 Stellen) + Icon + Einheit komfortabel inline passen
 * (auch bei vielen Kacheln nicht gequetscht) — die Ellipsis greift fast nie.
 * Optionaler
 * A6-FormelTooltip-Slot (`formel`/`berechnung`/`ergebnis`/`sicht`) — Optik aus dem
 * P3-Tooltip-Kanon (`FormelTooltip`). Ausbau des Herleitungs-Vertrags ist E4.
 *
 * Dokumentierter Sonderfall: `pages/community/KomponentenTab` hält eine eigene
 * Vergleichs-Kachel (community_avg-Delta) AUF dieser Farb-/Größen-Logik.
 */

import Card from './Card'
import FormelTooltip, { SimpleTooltip } from './FormelTooltip'
import { COLOR_CLASSES, type KomponentenColor } from '../../lib/komponentenStyle'

export interface KPICardProps {
  title: string
  value: string | number
  unit?: string
  subtitle?: string
  icon?: React.ElementType
  /** Datentyp-Farbe. In sm tönt sie den Wert; ohne Angabe bleibt der Wert neutral. In md/lg färbt sie die Icon-Box (Default blau). */
  color?: KomponentenColor
  size?: 'sm' | 'md' | 'lg'
  trend?: 'up' | 'down'
  onClick?: () => void
  // A6-Tooltip-Slot (Berechnungsdetails)
  formel?: string
  berechnung?: string
  ergebnis?: string
  sicht?: string
  /** Voraussetzungs-Hinweis bei fehlendem Wert („—"): erklärt im Tooltip, welche
   *  Zuordnung/welcher Sensor fehlt (Gernot 2026-06-24). Nur wirksam ohne `formel`. */
  hinweis?: string
}

export function KPICard({
  title,
  value,
  unit,
  subtitle,
  icon: Icon,
  color,
  size = 'md',
  trend,
  onClick,
  formel,
  berechnung,
  ergebnis,
  sicht,
  hinweis,
}: KPICardProps) {
  const formattedValue = typeof value === 'number' ? value.toLocaleString('de-DE') : value

  const trendMark =
    trend === 'up' ? <span className="ml-1 text-green-500">↑</span>
    : trend === 'down' ? <span className="ml-1 text-red-500">↓</span>
    : null

  // ── Kompaktform (sm): kein Icon-Kasten, der Wert trägt die Farbe ──────────────
  if (size === 'sm') {
    const valueColor = color ? COLOR_CLASSES[color].text : 'text-gray-900 dark:text-white'
    const iconColor = color ? COLOR_CLASSES[color].text : 'text-gray-500 dark:text-gray-400'
    const valueContent = (
      <span className={`text-sm font-semibold ${valueColor} inline-flex items-baseline max-w-full`}>
        <span className="flex-shrink-0 whitespace-nowrap">{formattedValue}{trendMark}</span>
        {unit && <span className="text-xs font-normal text-gray-500 dark:text-gray-400 ml-1 min-w-0 truncate">{unit}</span>}
      </span>
    )
    return (
      <div className="h-full bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-2">
        <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 mb-0.5">
          {Icon && <Icon className={`h-3.5 w-3.5 ${iconColor} flex-shrink-0`} />}
          <span className="truncate">{title}</span>
        </div>
        <div>
          {formel ? (
            <FormelTooltip formel={formel} berechnung={berechnung} ergebnis={ergebnis} sicht={sicht}>
              {valueContent}
            </FormelTooltip>
          ) : hinweis ? (
            <SimpleTooltip text={hinweis}>
              <span className="inline-flex items-baseline border-b border-dotted border-gray-300 dark:border-gray-600 cursor-help">{valueContent}</span>
            </SimpleTooltip>
          ) : (
            valueContent
          )}
        </div>
        {subtitle && (
          <p className="text-[11px] text-gray-400 dark:text-gray-500 mt-0.5 truncate">{subtitle}</p>
        )}
      </div>
    )
  }

  // ── Standard-/Prominent-Kachel (md/lg) mit farbiger Icon-Box ──────────────────
  const colors = COLOR_CLASSES[color ?? 'blue']
  const dims = {
    md: { value: 'text-xl sm:text-2xl', icon: 'h-5 w-5 sm:h-6 sm:w-6', box: 'p-2 sm:p-3' },
    lg: { value: 'text-2xl sm:text-3xl', icon: 'h-6 w-6 sm:h-7 sm:w-7', box: 'p-3' },
  }[size]

  const valueContent = (
    <span className={`${dims.value} font-bold text-gray-900 dark:text-white inline-flex items-baseline max-w-full`}>
      <span className="flex-shrink-0 whitespace-nowrap">{formattedValue}{trendMark}</span>
      {unit && <span className="text-xs sm:text-sm font-normal text-gray-500 dark:text-gray-400 ml-1 min-w-0 truncate">{unit}</span>}
    </span>
  )

  const inner = (
    <div className="flex items-start justify-between">
      <div className="flex-1 min-w-0">
        <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 truncate">{title}</p>
        <div className="mt-1">
          {formel ? (
            <FormelTooltip formel={formel} berechnung={berechnung} ergebnis={ergebnis} sicht={sicht}>
              {valueContent}
            </FormelTooltip>
          ) : hinweis ? (
            <SimpleTooltip text={hinweis}>
              <span className="inline-flex items-baseline border-b border-dotted border-gray-300 dark:border-gray-600 cursor-help">{valueContent}</span>
            </SimpleTooltip>
          ) : (
            valueContent
          )}
        </div>
        {subtitle && (
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1 truncate">{subtitle}</p>
        )}
      </div>
      {Icon && (
        <div className={`${dims.box} rounded-xl ${colors.bg} ml-2 sm:ml-3 flex-shrink-0`}>
          <Icon className={`${dims.icon} ${colors.text}`} />
        </div>
      )}
    </div>
  )

  if (onClick) {
    return (
      <button
        onClick={onClick}
        className="text-left w-full h-full rounded-xl transition-shadow hover:shadow-md focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        <Card className="h-full">{inner}</Card>
      </button>
    )
  }
  return <Card className="h-full">{inner}</Card>
}
