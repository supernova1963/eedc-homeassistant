/**
 * WerkbankZeitraum — block-interne, fest verankerte Zeitraum-/Vergleich-Leiste der
 * Werte-Werkbank (Gernot 2026-06-26: „im Block fixiert", nicht schwebend). Steht
 * oben im Block-Inhalt jedes Tabellen-Blocks; Granularität bestimmt das Eingabefeld
 * (Monat = `type=month`, Tag = `type=date`). Schnellwahl-Chips + freie von/bis-Wahl
 * (HA-artig: von/bis); Vergleich Aus|Vorjahr.
 */
import type { ReactNode } from 'react'

export interface ZeitChip {
  label: string
  /** liefert [von, bis] im passenden Format (YYYY-MM bzw. YYYY-MM-DD). */
  range: () => [string, string]
  /** aktiv-Markierung (optional, für den hervorgehobenen Chip). */
  aktiv?: boolean
}

export function WerkbankZeitraum({
  modus, von, bis, onRange, vergleich, onVergleich, vergleichSlot, chips, extra,
}: {
  modus: 'monat' | 'tag'
  von: string
  bis: string
  onRange: (von: string, bis: string) => void
  /** Einfacher Aus|Vorjahr-Schalter (Monats-Block). Ignoriert, wenn `vergleichSlot` gesetzt. */
  vergleich?: boolean
  onVergleich?: (an: boolean) => void
  /** Reicher Vergleichs-Selektor (z. B. {@link VergleichLeisteTag}) statt Aus|Vorjahr. */
  vergleichSlot?: ReactNode
  chips: ZeitChip[]
  /** optionaler Slot rechts (z. B. Status). */
  extra?: ReactNode
}) {
  const inputType = modus === 'monat' ? 'month' : 'date'
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/40 px-3 py-2">
      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          {chips.map((c) => (
            <button
              key={c.label}
              type="button"
              onClick={() => { const [v, b] = c.range(); onRange(v, b) }}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                c.aktiv
                  ? 'bg-primary-600 text-white'
                  : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
      )}

      <div className="flex items-center gap-1.5 text-sm">
        <span className="text-xs text-gray-500 dark:text-gray-400">Zeitraum</span>
        <input type={inputType} value={von} max={bis || undefined}
          onChange={(e) => onRange(e.target.value, bis)} aria-label="Von" className="input w-auto py-1 text-sm" />
        <span className="text-gray-400">–</span>
        <input type={inputType} value={bis} min={von || undefined}
          onChange={(e) => onRange(von, e.target.value)} aria-label="Bis" className="input w-auto py-1 text-sm" />
      </div>

      {vergleichSlot ? vergleichSlot : onVergleich && (
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500 dark:text-gray-400">Vergleich</span>
          <div className="inline-flex rounded-md border border-gray-200 dark:border-gray-700 overflow-hidden">
            <button type="button" onClick={() => onVergleich(false)}
              className={`px-2.5 py-1 text-xs font-medium transition-colors ${!vergleich ? 'bg-primary-600 text-white' : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'}`}>
              Aus
            </button>
            <button type="button" onClick={() => onVergleich(true)}
              className={`px-2.5 py-1 text-xs font-medium transition-colors ${vergleich ? 'bg-primary-600 text-white' : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'}`}>
              Vorjahr
            </button>
          </div>
        </div>
      )}

      {extra && <div className="ml-auto">{extra}</div>}
    </div>
  )
}

export type TagVergleichModus = 'vorperiode' | 'periodeImJahr'

/** Vergleichs-Selektor des Tageswerte-Blocks (Gernot 2026-06-27). Trennt sauber vom
 *  Primär-Zeitraum: der Vergleich ist immer **gleich lang wie der Primärbereich**:
 *   • **Vorperiode** — die gleich langen Tage direkt davor (Positions-Ausrichtung).
 *   • **Periode im Jahr** — derselbe Monats-/Tagesspann, nur ins gewählte Jahr
 *     verschoben (Kalender-Ausrichtung); Jahr aus dem Dropdown. Löst die alten
 *     fixen 30/90-Tage-Fenster ab. Ein-/Ausblenden läuft über den „Vergleich"-Knopf
 *     der Tabelle (dieser Selektor wählt nur den Typ). */
export function VergleichLeisteTag({
  modus, onModus, jahr, onJahr, jahre,
}: {
  modus: TagVergleichModus
  onModus: (m: TagVergleichModus) => void
  jahr: number
  onJahr: (j: number) => void
  jahre: number[]
}) {
  const chips: { k: TagVergleichModus; label: string }[] = [
    { k: 'vorperiode', label: 'Vorperiode' },
    { k: 'periodeImJahr', label: 'Periode im Jahr' },
  ]
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <span className="text-xs text-gray-500 dark:text-gray-400">Vergleich</span>
      <div className="flex flex-wrap items-center gap-1">
        {chips.map((c) => (
          <button key={c.k} type="button" onClick={() => onModus(c.k)}
            className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
              modus === c.k
                ? 'bg-primary-600 text-white'
                : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700'
            }`}>
            {c.label}
          </button>
        ))}
      </div>
      {modus === 'periodeImJahr' && (
        <select value={jahr} onChange={(e) => onJahr(Number(e.target.value))}
          aria-label="Vergleichsjahr" className="input w-auto py-1 text-sm">
          {jahre.map((j) => <option key={j} value={j}>{j}</option>)}
        </select>
      )}
    </div>
  )
}
