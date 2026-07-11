/**
 * WerkbankZeitraum — block-interne, fest verankerte Zeitraum-/Vergleich-Leiste der
 * Werte-Werkbank (Gernot 2026-06-26: „im Block fixiert", nicht schwebend). Steht
 * oben im Block-Inhalt jedes Tabellen-Blocks; Granularität bestimmt das Eingabefeld
 * (Monat = `type=month`, Tag = `type=date`). Schnellwahl-Chips + freie von/bis-Wahl
 * (HA-artig: von/bis); Vergleich Aus|Vorjahr.
 */
import type { ReactNode } from 'react'
import { DatumPicker } from '../components/ui/DatumPicker'
// STEUER_H (32-px-Toolbar-Höhe) lebt seit R3b S5 im lib-SoT-Modul `komponentenStyle`.
import { STEUER_H } from '../lib/komponentenStyle'
import { SegmentControl } from '../components/ui/SegmentControl'
import Select from '../components/ui/Select'

// D12-8: kleinerer/größerer der beiden ISO-Werte (lexikografisch, gilt für YYYY-MM
// wie YYYY-MM-DD) — `undefined`, wenn keiner gesetzt ist, damit `max`/`min` entfällt.
const kleinerVon = (a?: string, b?: string) => (a && b ? (a < b ? a : b) : a || b || undefined)
const groesserVon = (a?: string, b?: string) => (a && b ? (a > b ? a : b) : a || b || undefined)

export interface ZeitChip {
  label: string
  /** liefert [von, bis] im passenden Format (YYYY-MM bzw. YYYY-MM-DD). */
  range: () => [string, string]
  /** aktiv-Markierung (optional, für den hervorgehobenen Chip). */
  aktiv?: boolean
}

export function WerkbankZeitraum({
  modus, von, bis, onRange, vergleich, onVergleich, vergleichSlot, chips, extra, minDatum, maxDatum,
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
  /** D12-8: harte Untergrenze für beide Felder (YYYY-MM bzw. YYYY-MM-DD), je nach `modus`. */
  minDatum?: string
  /** D12-8: harte Obergrenze für beide Felder (YYYY-MM bzw. YYYY-MM-DD), je nach `modus`. */
  maxDatum?: string
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/40 px-3 py-2">
      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          {chips.map((c) => (
            <button
              key={c.label}
              type="button"
              onClick={() => { const [v, b] = c.range(); onRange(v, b) }}
              className={`px-2.5 ${STEUER_H} inline-flex items-center text-xs font-medium rounded-md transition-colors ${
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

      {/* D11-5: zwei type=month/date-Felder passen mobil nicht nebeneinander → auf
          schmal 2 Zeilen „Zeitraum von:/bis:" (Feld volle Breite), ab sm inline
          „Zeitraum [von] – [bis]". D11-4: Rand an die nicht-aktiven Chips angleichen. */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-1.5 text-sm w-full sm:w-auto">
        <span className="hidden sm:inline text-xs text-gray-500 dark:text-gray-400">Zeitraum</span>
        <label className="flex items-center gap-1.5 w-full sm:w-auto">
          <span className="sm:hidden text-xs text-gray-500 dark:text-gray-400 w-24 shrink-0">Zeitraum von:</span>
          {/* D12-8: von-Feld nach unten durch `minDatum` (ältester verfügbarer Zeitpunkt,
              analog CockpitTagV4 R5-F2), nach oben durch `bis`/`maxDatum` begrenzt —
              verhindert Phantasie-Jahre wie „1822". String-Vergleich gilt für YYYY-MM
              wie YYYY-MM-DD. D13-4/12: EIN Custom-DatumPicker (SoT) für Monat UND Tag
              — gleiches Icon/Stil app-weit statt Custom-Monat + nativem Tagesfeld. */}
          <DatumPicker modus={modus} value={von} min={minDatum} max={kleinerVon(bis, maxDatum)}
            onChange={(v) => onRange(v, bis)} ariaLabel="Von" className={`w-full sm:w-auto ${STEUER_H} text-sm`} />
        </label>
        <span className="hidden sm:inline text-gray-400 dark:text-gray-500">–</span>
        <label className="flex items-center gap-1.5 w-full sm:w-auto">
          <span className="sm:hidden text-xs text-gray-500 dark:text-gray-400 w-24 shrink-0">Zeitraum bis:</span>
          {/* D12-8: bis-Feld nach unten durch `von`/`minDatum`, nach oben durch `maxDatum`. */}
          <DatumPicker modus={modus} value={bis} min={groesserVon(von, minDatum)} max={maxDatum}
            onChange={(v) => onRange(von, v)} ariaLabel="Bis" className={`w-full sm:w-auto ${STEUER_H} text-sm`} />
        </label>
      </div>

      {vergleichSlot ? vergleichSlot : onVergleich && (
        <div className="flex items-center gap-1.5">
          <span className="text-xs text-gray-500 dark:text-gray-400">Vergleich</span>
          <SegmentControl
            ariaLabel="Vergleich" size="sm" radius="md"
            optionen={[{ key: 'aus', label: 'Aus' }, { key: 'vorjahr', label: 'Vorjahr' }]}
            value={vergleich ? 'vorjahr' : 'aus'}
            onChange={(k) => onVergleich(k === 'vorjahr')}
          />
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
            className={`px-2.5 ${STEUER_H} inline-flex items-center text-xs font-medium rounded-md transition-colors ${
              modus === c.k
                ? 'bg-primary-600 text-white'
                : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700'
            }`}>
            {c.label}
          </button>
        ))}
      </div>
      {modus === 'periodeImJahr' && (
        <Select
          steuer
          value={String(jahr)} onChange={(e) => onJahr(Number(e.target.value))}
          aria-label="Vergleichsjahr"
          options={jahre.map((j) => ({ value: String(j), label: String(j) }))}
        />
      )}
    </div>
  )
}
