// TabelleTab - Interaktiver Energie-Explorer: Tabellenansicht mit Filter, Sortierung, Spaltenauswahl
import { useState, useMemo, useRef, useEffect, Fragment } from 'react'
import { Download, ChevronUp, ChevronDown, ChevronsUpDown, Columns, GitCompareArrows } from 'lucide-react'
import { Card, Button } from '../../components/ui'
import { exportToCSV } from '../../utils/export'
import type { AggregierteMonatsdaten } from '../../api/monatsdaten'
import { TabProps, createMonatsZeitreihe, MonatsZeitreihe } from './types'

const MONTH_NAMES = ['', 'Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']
const STORAGE_KEY = 'eedc_tabelle_visible_cols'

type AggType = 'sum' | 'avg' | 'none'
type Group = 'basis' | 'quoten' | 'speicher' | 'waermepumpe' | 'eauto' | 'finanzen' | 'co2'

interface ColumnDef {
  key: string
  label: string
  unit: string
  group: Group
  decimals: number
  aggregation: AggType
  defaultVisible: boolean
  higherIsBetter?: boolean  // für Vorjahr-Farbgebung: true = grün wenn +, false = grün wenn -
}

const COLUMNS: ColumnDef[] = [
  // Energie
  { key: 'erzeugung',         label: 'PV-Erzeugung',      unit: 'kWh',     group: 'basis',       decimals: 0, aggregation: 'sum', defaultVisible: true,  higherIsBetter: true  },
  { key: 'eigenverbrauch',    label: 'Eigenverbrauch',     unit: 'kWh',     group: 'basis',       decimals: 0, aggregation: 'sum', defaultVisible: true,  higherIsBetter: true  },
  { key: 'einspeisung',       label: 'Einspeisung',        unit: 'kWh',     group: 'basis',       decimals: 0, aggregation: 'sum', defaultVisible: true,  higherIsBetter: true  },
  { key: 'netzbezug',         label: 'Netzbezug',          unit: 'kWh',     group: 'basis',       decimals: 0, aggregation: 'sum', defaultVisible: true,  higherIsBetter: false },
  { key: 'gesamtverbrauch',   label: 'Gesamtverbrauch',    unit: 'kWh',     group: 'basis',       decimals: 0, aggregation: 'sum', defaultVisible: false, higherIsBetter: undefined },
  { key: 'direktverbrauch',   label: 'Direktverbrauch',    unit: 'kWh',     group: 'basis',       decimals: 0, aggregation: 'sum', defaultVisible: false, higherIsBetter: true  },
  // Quoten
  { key: 'autarkie',          label: 'Autarkie',           unit: '%',       group: 'quoten',      decimals: 1, aggregation: 'avg', defaultVisible: true,  higherIsBetter: true  },
  { key: 'evQuote',           label: 'EV-Quote',           unit: '%',       group: 'quoten',      decimals: 1, aggregation: 'avg', defaultVisible: true,  higherIsBetter: true  },
  { key: 'spezErtrag',        label: 'Spez. Ertrag',       unit: 'kWh/kWp', group: 'quoten',      decimals: 0, aggregation: 'sum', defaultVisible: false, higherIsBetter: true  },
  // Speicher
  { key: 'speicher_ladung',   label: 'Speicher Ladung',    unit: 'kWh',     group: 'speicher',    decimals: 0, aggregation: 'sum', defaultVisible: false, higherIsBetter: undefined },
  { key: 'speicher_entladung',label: 'Speicher Entladung', unit: 'kWh',     group: 'speicher',    decimals: 0, aggregation: 'sum', defaultVisible: false, higherIsBetter: undefined },
  { key: 'speicher_effizienz',label: 'Speicher Effizienz', unit: '%',       group: 'speicher',    decimals: 1, aggregation: 'avg', defaultVisible: false, higherIsBetter: true  },
  // Wärmepumpe
  { key: 'wp_strom',          label: 'WP Strom',           unit: 'kWh',     group: 'waermepumpe', decimals: 0, aggregation: 'sum', defaultVisible: false, higherIsBetter: undefined },
  { key: 'wp_waerme',         label: 'WP Wärme',           unit: 'kWh',     group: 'waermepumpe', decimals: 0, aggregation: 'sum', defaultVisible: false, higherIsBetter: true  },
  { key: 'wp_cop',            label: 'WP COP',             unit: '',        group: 'waermepumpe', decimals: 1, aggregation: 'avg', defaultVisible: false, higherIsBetter: true  },
  // E-Auto
  { key: 'eauto_km',          label: 'E-Auto',             unit: 'km',      group: 'eauto',       decimals: 0, aggregation: 'sum', defaultVisible: false, higherIsBetter: undefined },
  { key: 'eauto_ladung',      label: 'E-Auto Ladung',      unit: 'kWh',     group: 'eauto',       decimals: 0, aggregation: 'sum', defaultVisible: false, higherIsBetter: undefined },
  // Finanzen — Berechnung via createMonatsZeitreihe mit historisch korrektem Tarif pro Monat
  { key: 'einspeise_erloes',  label: 'Einspeise-Erlös',    unit: '€',       group: 'finanzen',    decimals: 2, aggregation: 'sum', defaultVisible: false, higherIsBetter: true  },
  { key: 'ev_ersparnis',      label: 'EV-Ersparnis',       unit: '€',       group: 'finanzen',    decimals: 2, aggregation: 'sum', defaultVisible: false, higherIsBetter: true  },
  { key: 'netzbezug_kosten',  label: 'Netzbezug-Kosten',   unit: '€',       group: 'finanzen',    decimals: 2, aggregation: 'sum', defaultVisible: false, higherIsBetter: false },
  { key: 'netto_ertrag',      label: 'Netto-Ertrag',       unit: '€',       group: 'finanzen',    decimals: 2, aggregation: 'sum', defaultVisible: false, higherIsBetter: true  },
  // CO2
  { key: 'co2_einsparung',    label: 'CO₂-Einsparung',     unit: 'kg',      group: 'co2',         decimals: 1, aggregation: 'sum', defaultVisible: false, higherIsBetter: true  },
]

const GROUP_LABELS: Record<Group, string> = {
  basis:       'Energie',
  quoten:      'Quoten',
  speicher:    'Speicher',
  waermepumpe: 'Wärmepumpe',
  eauto:       'E-Auto',
  finanzen:    'Finanzen',
  co2:         'CO₂',
}

const GROUPS: Group[] = ['basis', 'quoten', 'speicher', 'waermepumpe', 'eauto', 'finanzen', 'co2']

function fmtVal(v: number | null, decimals: number): string {
  if (v == null) return '—'
  return v.toLocaleString('de-DE', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

type SortKey = 'jahr' | 'monat' | string
type RowData = Record<string, number | null>

interface TabelleTabProps extends TabProps {
  alleDaten: AggregierteMonatsdaten[]
  selectedYear: number | 'all'
}

export function TabelleTab({ data, anlage, strompreis, alleTarife, zeitraumLabel, alleDaten, selectedYear }: TabelleTabProps) {
  const [sortKey, setSortKey] = useState<SortKey>('jahr')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')
  const [visibleCols, setVisibleCols] = useState<Set<string>>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) {
        const keys = JSON.parse(stored) as string[]
        const valid = keys.filter(k => COLUMNS.some(c => c.key === k))
        if (valid.length > 0) return new Set(valid)
      }
    } catch { /* ignore */ }
    return new Set(COLUMNS.filter(c => c.defaultVisible).map(c => c.key))
  })
  const [showVorjahr, setShowVorjahr] = useState(false)
  const [compareYear, setCompareYear] = useState<number | null>(null)
  const [colPickerOpen, setColPickerOpen] = useState(false)
  const pickerRef = useRef<HTMLDivElement>(null)

  // Spaltenauswahl in localStorage speichern
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify([...visibleCols]))
    } catch { /* ignore */ }
  }, [visibleCols])

  // Picker bei Klick außerhalb schließen
  useEffect(() => {
    function onOutsideClick(e: MouseEvent) {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setColPickerOpen(false)
      }
    }
    if (colPickerOpen) document.addEventListener('mousedown', onOutsideClick)
    return () => document.removeEventListener('mousedown', onOutsideClick)
  }, [colPickerOpen])

  // Verfügbare Vergleichsjahre (alle Jahre außer dem gewählten, neueste zuerst)
  const availableCompareYears = useMemo(() => {
    if (selectedYear === 'all') return []
    return [...new Set(alleDaten.map(d => d.jahr))]
      .filter(y => y !== selectedYear)
      .sort((a, b) => b - a)
  }, [alleDaten, selectedYear])

  // compareYear bei Jahreswechsel auto-setzen (Vorjahr bevorzugen)
  useEffect(() => {
    if (selectedYear === 'all' || availableCompareYears.length === 0) {
      setCompareYear(null)
      return
    }
    const prevYear = (selectedYear as number) - 1
    if (availableCompareYears.includes(prevYear)) {
      setCompareYear(prevYear)
    } else {
      setCompareYear(availableCompareYears[0])
    }
  }, [selectedYear, availableCompareYears])

  const zeitreihe = useMemo(
    () => createMonatsZeitreihe(data, anlage, strompreis, alleTarife),
    [data, anlage, strompreis, alleTarife]
  )

  // Vorjahresdaten — createMonatsZeitreihe nutzt alleTarife für historisch korrekte Tarife
  const vorjahrLookup = useMemo<Record<number, MonatsZeitreihe> | null>(() => {
    if (!showVorjahr || selectedYear === 'all' || compareYear === null) return null
    const prevData = alleDaten.filter(d => d.jahr === compareYear)
    if (prevData.length === 0) return null
    const prevZeitreihe = createMonatsZeitreihe(prevData, anlage, strompreis, alleTarife)
    return Object.fromEntries(prevZeitreihe.map(r => [r.monat, r]))
  }, [showVorjahr, selectedYear, compareYear, alleDaten, anlage, strompreis, alleTarife])

  const vorjahrVerfuegbar = selectedYear !== 'all' && compareYear !== null && vorjahrLookup !== null

  // Sortierte Zeilen
  const sortedRows = useMemo(() => {
    return [...zeitreihe].sort((a, b) => {
      let av: number
      let bv: number
      if (sortKey === 'jahr')       { av = a.jahr;  bv = b.jahr  }
      else if (sortKey === 'monat') { av = a.monat; bv = b.monat }
      else {
        av = ((a as unknown as RowData)[sortKey] ?? -Infinity) as number
        bv = ((b as unknown as RowData)[sortKey] ?? -Infinity) as number
      }
      return sortDir === 'asc' ? av - bv : bv - av
    })
  }, [zeitreihe, sortKey, sortDir])

  // Aggregationszeile
  const aggregation = useMemo(() => {
    const result: Record<string, number | null> = {}
    for (const col of COLUMNS) {
      const vals = zeitreihe
        .map(r => (r as unknown as RowData)[col.key])
        .filter((v): v is number => v != null)
      if (vals.length === 0) { result[col.key] = null; continue }
      if (col.aggregation === 'sum')      result[col.key] = vals.reduce((s, v) => s + v, 0)
      else if (col.aggregation === 'avg') result[col.key] = vals.reduce((s, v) => s + v, 0) / vals.length
      else                                result[col.key] = null
    }
    return result
  }, [zeitreihe])

  function handleSort(key: SortKey) {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('asc') }
  }

  function toggleCol(key: string) {
    setVisibleCols(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  function handleExport() {
    const activeCols = COLUMNS.filter(c => visibleCols.has(c.key))
    const headers: string[] = ['Jahr', 'Monat']
    activeCols.forEach(c => {
      headers.push(c.unit ? `${c.label} (${c.unit})` : c.label)
      if (vorjahrVerfuegbar) headers.push(`Δ vs. ${compareYear}`)
    })

    const rows: (string | number)[][] = sortedRows.map(r => {
      const prevRow = vorjahrLookup?.[r.monat]
      const row: (string | number)[] = [r.jahr, MONTH_NAMES[r.monat]]
      activeCols.forEach(c => {
        const v = (r as unknown as RowData)[c.key]
        row.push(v != null ? v : '')
        if (vorjahrVerfuegbar) {
          const pv = prevRow ? (prevRow as unknown as RowData)[c.key] : null
          const delta = v != null && pv != null ? v - pv : null
          row.push(delta != null ? delta : '')
        }
      })
      return row
    })

    // Aggregationszeile
    const aggRow: (string | number)[] = [
      zeitreihe.length > 0
        ? `${Math.min(...zeitreihe.map(r => r.jahr))}–${Math.max(...zeitreihe.map(r => r.jahr))}`
        : '',
      `${zeitreihe.length} Monate`,
    ]
    activeCols.forEach(c => {
      const v = aggregation[c.key]
      aggRow.push(v != null ? v : '')
      if (vorjahrVerfuegbar) aggRow.push('')
    })
    rows.push(aggRow)

    exportToCSV(headers, rows, `energie_tabelle_${anlage?.anlagenname || 'export'}.csv`)
  }

  const activeCols = COLUMNS.filter(c => visibleCols.has(c.key))
  const canShowVorjahr = selectedYear !== 'all'

  function SortIcon({ colKey }: { colKey: string }) {
    if (sortKey !== colKey) return <ChevronsUpDown className="h-3 w-3 opacity-30 shrink-0" />
    return sortDir === 'asc'
      ? <ChevronUp className="h-3 w-3 text-primary-500 shrink-0" />
      : <ChevronDown className="h-3 w-3 text-primary-500 shrink-0" />
  }

  function DeltaCell({ current, prev, col }: { current: number | null; prev: number | null; col: ColumnDef }) {
    if (current == null || prev == null) return <span className="text-gray-300 dark:text-gray-600">—</span>
    const delta = current - prev
    const deltaPct = prev !== 0 ? (delta / Math.abs(prev)) * 100 : null
    const isPositive = delta > 0
    const isNeutral = delta === 0
    const isGood = col.higherIsBetter === undefined
      ? isNeutral
      : col.higherIsBetter ? isPositive : !isPositive

    const colorClass = isNeutral
      ? 'text-gray-400 dark:text-gray-500'
      : isGood
        ? 'text-green-600 dark:text-green-400'
        : 'text-red-500 dark:text-red-400'

    return (
      <span className={colorClass}>
        {isPositive ? '▲' : delta < 0 ? '▼' : '='} {fmtVal(Math.abs(delta), col.decimals)}
        {deltaPct != null && (
          <span className="ml-1 opacity-75">({deltaPct > 0 ? '+' : ''}{deltaPct.toFixed(1)}%)</span>
        )}
      </span>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-sm text-gray-500 dark:text-gray-400">
          <span className="font-medium text-gray-700 dark:text-gray-300">{zeitraumLabel}</span>
          {' '}·{' '}{zeitreihe.length} Monate
          {vorjahrVerfuegbar && showVorjahr && (
            <span className="ml-2 text-primary-500 dark:text-primary-400">
              · Vergleich mit {compareYear}
            </span>
          )}
        </p>
        <div className="flex items-center gap-2 flex-wrap">

          {/* Vorjahr-Vergleich Toggle + Jahresauswahl */}
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => canShowVorjahr && setShowVorjahr(v => !v)}
              title={!canShowVorjahr ? 'Bitte ein konkretes Jahr auswählen' : undefined}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
                !canShowVorjahr
                  ? 'border-gray-200 dark:border-gray-700 text-gray-300 dark:text-gray-600 cursor-not-allowed'
                  : showVorjahr
                    ? 'border-primary-300 bg-primary-50 text-primary-700 dark:border-primary-700 dark:bg-primary-900/30 dark:text-primary-300'
                    : 'border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800'
              }`}
            >
              <GitCompareArrows className="h-3.5 w-3.5" />
              Jahresvergleich
            </button>
            {showVorjahr && canShowVorjahr && availableCompareYears.length > 0 && (
              <select
                value={compareYear ?? ''}
                onChange={e => setCompareYear(Number(e.target.value))}
                title="Vergleichsjahr auswählen"
                className="text-xs px-2 py-1.5 rounded-lg border border-primary-300 dark:border-primary-700 bg-primary-50 dark:bg-gray-800 text-primary-700 dark:text-primary-300 focus:outline-none focus:ring-1 focus:ring-primary-400"
              >
                {availableCompareYears.map(y => (
                  <option key={y} value={y}>vs. {y}</option>
                ))}
              </select>
            )}
          </div>

          {/* Spaltenauswahl */}
          <div className="relative" ref={pickerRef}>
            <Button variant="secondary" size="sm" onClick={() => setColPickerOpen(o => !o)}>
              <Columns className="h-4 w-4 mr-2" />
              Spalten ({visibleCols.size})
            </Button>
            {colPickerOpen && (
              <div className="absolute right-0 top-full mt-1 z-20 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg p-3 w-52 max-h-96 overflow-y-auto">
                {GROUPS.map(group => {
                  const groupCols = COLUMNS.filter(c => c.group === group)
                  return (
                    <div key={group} className="mb-3 last:mb-0">
                      <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide mb-1">
                        {GROUP_LABELS[group]}
                      </p>
                      {groupCols.map(col => (
                        <label key={col.key} className="flex items-center gap-2 py-0.5 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={visibleCols.has(col.key)}
                            onChange={() => toggleCol(col.key)}
                            className="rounded"
                          />
                          <span className="text-sm text-gray-700 dark:text-gray-300">
                            {col.label}{col.unit ? ` (${col.unit})` : ''}
                          </span>
                        </label>
                      ))}
                    </div>
                  )
                })}
              </div>
            )}
          </div>

          {/* CSV Export */}
          <Button variant="secondary" size="sm" onClick={handleExport}>
            <Download className="h-4 w-4 mr-2" />
            CSV Export
          </Button>
        </div>
      </div>

      {/* Hinweis wenn Vorjahr aktiv aber keine Daten */}
      {showVorjahr && canShowVorjahr && !vorjahrVerfuegbar && compareYear !== null && (
        <p className="text-xs text-amber-600 dark:text-amber-400">
          Keine Daten für {compareYear} vorhanden.
        </p>
      )}
      {showVorjahr && canShowVorjahr && availableCompareYears.length === 0 && (
        <p className="text-xs text-amber-600 dark:text-amber-400">
          Keine weiteren Jahre für einen Vergleich vorhanden.
        </p>
      )}

      {/* Tabelle */}
      <Card padding="none" className="overflow-hidden">
        <div className="overflow-auto max-h-[600px]">
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-10">
              <tr className="border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
                <th
                  className="px-3 py-2.5 text-left font-medium text-gray-500 dark:text-gray-400 cursor-pointer hover:text-gray-800 dark:hover:text-gray-200 whitespace-nowrap select-none"
                  onClick={() => handleSort('jahr')}
                >
                  <span className="flex items-center gap-1">Jahr <SortIcon colKey="jahr" /></span>
                </th>
                <th
                  className="px-3 py-2.5 text-left font-medium text-gray-500 dark:text-gray-400 cursor-pointer hover:text-gray-800 dark:hover:text-gray-200 whitespace-nowrap select-none"
                  onClick={() => handleSort('monat')}
                >
                  <span className="flex items-center gap-1">Monat <SortIcon colKey="monat" /></span>
                </th>
                {activeCols.map(col => (
                  <th
                    key={col.key}
                    className={`px-3 py-2.5 text-right font-medium text-gray-500 dark:text-gray-400 cursor-pointer hover:text-gray-800 dark:hover:text-gray-200 whitespace-nowrap select-none ${
                      vorjahrVerfuegbar && showVorjahr ? 'border-r border-gray-200 dark:border-gray-700' : ''
                    }`}
                    colSpan={vorjahrVerfuegbar && showVorjahr ? 2 : 1}
                    onClick={() => handleSort(col.key)}
                  >
                    <span className="flex items-center justify-end gap-1">
                      {col.label}{col.unit ? ` (${col.unit})` : ''}
                      <SortIcon colKey={col.key} />
                    </span>
                  </th>
                ))}
              </tr>
              {/* Vorjahr-Subheader */}
              {vorjahrVerfuegbar && showVorjahr && (
                <tr className="border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
                  <td colSpan={2} />
                  {activeCols.map(col => (
                    <Fragment key={col.key}>
                      <td className="px-3 py-1 text-right text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">
                        {selectedYear as number}
                      </td>
                      <td className="px-3 py-1 text-right text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap border-r border-gray-200 dark:border-gray-700">
                        Δ vs. {compareYear}
                      </td>
                    </Fragment>
                  ))}
                </tr>
              )}
            </thead>
            <tbody>
              {sortedRows.map((row, i) => {
                const prevRow = vorjahrLookup?.[row.monat] ?? null
                return (
                  <tr
                    key={`${row.jahr}-${row.monat}`}
                    className={`border-b border-gray-100 dark:border-gray-800 hover:bg-primary-50/30 dark:hover:bg-primary-900/10 transition-colors ${
                      i % 2 !== 0 ? 'bg-gray-50/50 dark:bg-gray-800/20' : ''
                    }`}
                  >
                    <td className="px-3 py-2 font-medium text-gray-900 dark:text-white">{row.jahr}</td>
                    <td className="px-3 py-2 text-gray-700 dark:text-gray-300">{MONTH_NAMES[row.monat]}</td>
                    {activeCols.map(col => {
                      const v = (row as unknown as RowData)[col.key]
                      const pv = prevRow ? (prevRow as unknown as RowData)[col.key] : null
                      if (vorjahrVerfuegbar && showVorjahr) {
                        return (
                          <Fragment key={col.key}>
                            <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">
                              {fmtVal(v, col.decimals)}
                            </td>
                            <td className="px-3 py-2 text-right tabular-nums text-xs border-r border-gray-100 dark:border-gray-800">
                              <DeltaCell current={v} prev={pv} col={col} />
                            </td>
                          </Fragment>
                        )
                      }
                      return (
                        <td key={col.key} className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">
                          {fmtVal(v, col.decimals)}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>

            {/* Aggregationszeile */}
            {sortedRows.length > 1 && (
              <tfoot>
                <tr className="border-t-2 border-gray-300 dark:border-gray-600 bg-gray-100 dark:bg-gray-700/50">
                  <td
                    className="px-3 py-2.5 font-semibold text-gray-600 dark:text-gray-300 text-xs uppercase tracking-wide"
                    colSpan={2}
                  >
                    {zeitreihe.length === 12 ? 'Gesamt / Ø' : `${zeitreihe.length} Monate`}
                  </td>
                  {activeCols.map(col => {
                    const v = aggregation[col.key]
                    const prefix = col.aggregation === 'avg' ? 'Ø ' : ''
                    if (vorjahrVerfuegbar && showVorjahr) {
                      return (
                        <Fragment key={col.key}>
                          <td className="px-3 py-2.5 text-right tabular-nums font-semibold text-gray-800 dark:text-gray-100">
                            {v != null ? `${prefix}${fmtVal(v, col.decimals)}` : '—'}
                          </td>
                          <td className="px-3 py-2.5 border-r border-gray-300 dark:border-gray-600" />
                        </Fragment>
                      )
                    }
                    return (
                      <td key={col.key} className="px-3 py-2.5 text-right tabular-nums font-semibold text-gray-800 dark:text-gray-100">
                        {v != null ? `${prefix}${fmtVal(v, col.decimals)}` : '—'}
                      </td>
                    )
                  })}
                </tr>
              </tfoot>
            )}
          </table>

          {sortedRows.length === 0 && (
            <div className="py-12 text-center text-gray-400 dark:text-gray-500">
              Keine Daten für den gewählten Zeitraum.
            </div>
          )}
        </div>
      </Card>
    </div>
  )
}
