/**
 * TagWerteTabelle — Stundenwerte-Tabelle eines Tages (24 Zeilen, Σ = kWh/Tag).
 *
 * Aus der IST-„Tagesdetail"-Sicht (`pages/auswertung/EnergieprofilTab.tsx`)
 * extrahiert (hieß dort `TagesdetailTabelle`), damit Cockpit/Tag (v4) und die
 * IST-Seite EINE Code-Wahrheit teilen (Konvergenz). Spalten-Picker (localStorage),
 * Sortierung, CSV-Export, Summenzeile. Reine Darstellung aus `StundenWert[]`.
 */
import { useState, useEffect, useMemo, useRef } from 'react'
import { Download, ChevronUp, ChevronDown, ChevronsUpDown, Columns } from 'lucide-react'
import { Card, Button } from '../ui'
import { exportToCSV } from '../../utils/export'
import type { StundenWert, SerieInfo } from '../../api/energie_profil'

function round2(v: number): number {
  return Math.round(v * 100) / 100
}

type TdGroup = 'erzeugung' | 'netz' | 'verbrauch' | 'bilanz' | 'qualitaet'

interface TdColDef {
  key: string
  label: string
  unit: string
  group: TdGroup
  decimals: number
  isSum: boolean        // kW × 1h = kWh in Summenzeile
  defaultVisible: boolean
  calc?: boolean        // berechnete Spalte (kein direktes StundenWert-Feld)
}

const TD_COLUMNS: TdColDef[] = [
  // Erzeugung
  { key: 'gesamterzeugung', label: 'Verfügbare Energie', unit: 'kW', group: 'erzeugung', decimals: 2, isSum: true,  defaultVisible: true,  calc: true  },
  { key: 'pv_kw',           label: 'PV',              unit: 'kW', group: 'erzeugung', decimals: 2, isSum: true,  defaultVisible: true                },
  { key: 'batterie_kw',     label: 'Batterie',        unit: 'kW', group: 'erzeugung', decimals: 2, isSum: true,  defaultVisible: true                },
  // Netz
  { key: 'netzbezug_kw',   label: 'Netzbezug',       unit: 'kW', group: 'netz',      decimals: 2, isSum: true,  defaultVisible: true                },
  { key: 'einspeisung_kw', label: 'Einspeisung',     unit: 'kW', group: 'netz',      decimals: 2, isSum: true,  defaultVisible: false               },
  // Verbrauch
  { key: 'verbrauch_kw',   label: 'Gesamtverbrauch', unit: 'kW', group: 'verbrauch', decimals: 2, isSum: true,  defaultVisible: true                },
  { key: 'hausverbrauch',  label: 'Hausverbrauch',   unit: 'kW', group: 'verbrauch', decimals: 2, isSum: true,  defaultVisible: true,  calc: true   },
  { key: 'waermepumpe_kw', label: 'Wärmepumpe',      unit: 'kW', group: 'verbrauch', decimals: 2, isSum: true,  defaultVisible: true                },
  { key: 'wp_starts_anzahl', label: 'WP-Starts',     unit: '',   group: 'verbrauch', decimals: 0, isSum: true,  defaultVisible: false               },
  { key: 'wp_betriebsstunden', label: 'WP-Betriebsstd.', unit: 'h', group: 'verbrauch', decimals: 2, isSum: true, defaultVisible: false             },
  { key: 'wallbox_kw',     label: 'Wallbox',         unit: 'kW', group: 'verbrauch', decimals: 2, isSum: true,  defaultVisible: true                },
  // Bilanz
  { key: 'ueberschuss_kw', label: 'Überschuss',      unit: 'kW', group: 'bilanz',    decimals: 2, isSum: true,  defaultVisible: false               },
  { key: 'defizit_kw',     label: 'Defizit',         unit: 'kW', group: 'bilanz',    decimals: 2, isSum: true,  defaultVisible: false               },
  // Qualität
  { key: 'soc_prozent',        label: 'SoC',         unit: '%',    group: 'qualitaet', decimals: 1, isSum: false, defaultVisible: false             },
  { key: 'temperatur_c',       label: 'Temperatur',  unit: '°C',   group: 'qualitaet', decimals: 1, isSum: false, defaultVisible: false             },
  { key: 'globalstrahlung_wm2',label: 'Strahlung',   unit: 'W/m²', group: 'qualitaet', decimals: 0, isSum: false, defaultVisible: false             },
]

const TD_GROUP_LABELS: Record<TdGroup, string> = {
  erzeugung: 'Erzeugung',
  netz:      'Netz',
  verbrauch: 'Verbrauch',
  bilanz:    'Bilanz',
  qualitaet: 'Qualität',
}
const TD_GROUPS: TdGroup[] = ['erzeugung', 'netz', 'verbrauch', 'bilanz', 'qualitaet']
const TD_STORAGE_KEY = 'eedc_tagesprofil_visible_cols'

export function TagWerteTabelle({ daten, extraSerien, datum }: { daten: StundenWert[], extraSerien: SerieInfo[], datum: string }) {
  const extraErzeuger    = extraSerien.filter(s => s.seite === 'quelle')
  const extraVerbraucher = extraSerien.filter(s => s.seite === 'senke')

  // Berechnete Werte pro Stunde
  function calcGesamterzeugung(s: StundenWert): number {
    const erzS = extraErzeuger.reduce((a, es) => a + Math.max(0, s.komponenten?.[es.key] ?? 0), 0)
    return round2((s.pv_kw ?? 0) + Math.max(0, s.batterie_kw ?? 0) + erzS)
  }
  function calcHausverbrauch(s: StundenWert): number {
    const vbrS = extraVerbraucher.reduce((a, es) => a + Math.abs(Math.min(0, s.komponenten?.[es.key] ?? 0)), 0)
    return round2(Math.max(0, (s.verbrauch_kw ?? 0) - (s.waermepumpe_kw ?? 0) - (s.wallbox_kw ?? 0) - vbrS))
  }

  // Sichtbare Spalten aus localStorage
  const [visibleCols, setVisibleCols] = useState<Set<string>>(() => {
    try {
      const stored = localStorage.getItem(TD_STORAGE_KEY)
      if (stored) {
        const keys = JSON.parse(stored) as string[]
        return new Set(keys)
      }
    } catch { /* ignore */ }
    const defaults = new Set(TD_COLUMNS.filter(c => c.defaultVisible).map(c => c.key))
    extraSerien.forEach(es => defaults.add(es.key))
    return defaults
  })
  useEffect(() => {
    // Neue extra Serien immer als sichtbar hinzufügen
    setVisibleCols(prev => {
      const next = new Set(prev)
      extraSerien.forEach(es => { if (!next.has(es.key)) next.add(es.key) })
      return next
    })
  }, [extraSerien])
  useEffect(() => {
    try { localStorage.setItem(TD_STORAGE_KEY, JSON.stringify([...visibleCols])) } catch { /* ignore */ }
  }, [visibleCols])

  function toggleCol(key: string) {
    setVisibleCols(prev => { const n = new Set(prev); n.has(key) ? n.delete(key) : n.add(key); return n })
  }

  // Spaltenauswahl-Picker
  const [pickerOpen, setPickerOpen] = useState(false)
  const pickerRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    function onOut(e: MouseEvent) {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) setPickerOpen(false)
    }
    if (pickerOpen) document.addEventListener('mousedown', onOut)
    return () => document.removeEventListener('mousedown', onOut)
  }, [pickerOpen])

  // Sortierung
  const [sortKey, setSortKey] = useState<string | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  function handleSort(key: string) {
    if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setSortDir('desc') }
  }

  // Stunden-Daten (0-23, mit berechneten Feldern)
  const rows = useMemo(() => {
    const all = Array.from({ length: 24 }, (_, h) => {
      const s = daten.find(d => d.stunde === h)
      const raw = s ? (s as unknown as Record<string, number | null>) : {}
      return {
        h,
        s,
        vals: {
          ...raw,
          gesamterzeugung: s ? calcGesamterzeugung(s) : null,
          hausverbrauch:   s ? calcHausverbrauch(s)   : null,
          ...Object.fromEntries(extraSerien.map(es => [es.key, s?.komponenten?.[es.key] ?? null])),
        } as Record<string, number | null>,
      }
    })
    if (!sortKey) return all
    return [...all].sort((a, b) => {
      const av = a.vals[sortKey] ?? (sortDir === 'desc' ? -Infinity : Infinity)
      const bv = b.vals[sortKey] ?? (sortDir === 'desc' ? -Infinity : Infinity)
      return sortDir === 'asc' ? av - bv : bv - av
    })
  }, [daten, sortKey, sortDir, extraSerien])

  // Aktive Spalten in Reihenfolge: TD_COLUMNS + extra Serien (eingebettet in Gruppe)
  const allCols = useMemo(() => {
    const cols: (TdColDef | (SerieInfo & { unit: string; decimals: number; isSum: boolean; group: TdGroup }))[] = []
    for (const c of TD_COLUMNS) {
      cols.push(c)
      if (c.key === 'batterie_kw') extraErzeuger.forEach(es => cols.push({ ...es, unit: 'kW', decimals: 2, isSum: true, group: 'erzeugung' }))
      if (c.key === 'wallbox_kw') extraVerbraucher.forEach(es => cols.push({ ...es, unit: 'kW', decimals: 2, isSum: true, group: 'verbrauch' }))
    }
    return cols.filter(c => visibleCols.has(c.key))
  }, [visibleCols, extraErzeuger, extraVerbraucher])

  // Summenzeile
  const summen = useMemo(() => {
    const r: Record<string, number | null> = {}
    for (const col of allCols) {
      if (!col.isSum) { r[col.key] = null; continue }
      const vals = rows.map(row => row.vals[col.key]).filter(v => v != null) as number[]
      r[col.key] = vals.length ? vals.reduce((a, b) => a + b, 0) : null
    }
    return r
  }, [rows, allCols])

  // CSV Export
  function handleExport() {
    const headers = ['Stunde', ...allCols.map(c => c.unit ? `${c.label} (${c.unit})` : c.label)]
    const csvRows = rows.map(row => [
      `${row.h}:00`,
      ...allCols.map(c => {
        const v = row.vals[c.key]
        return v != null ? v.toFixed(c.decimals) : '' /* de-de-allow: CSV-Zellenwert (maschinenlesbar, kein Display) */
      }),
    ])
    // Summenzeile
    csvRows.push(['Σ/kWh', ...allCols.map(c => {
      const v = summen[c.key]
      return v != null ? v.toFixed(c.decimals) : '—' /* de-de-allow: CSV-Zellenwert (maschinenlesbar, kein Display) */
    })])
    exportToCSV(headers, csvRows, `energieprofil_${datum}.csv`) /* de-de-allow: Dateiname (ISO sortierbar) */
  }

  function SortIcon({ colKey }: { colKey: string }) {
    if (sortKey !== colKey) return <ChevronsUpDown className="h-3 w-3 opacity-30 shrink-0" />
    return sortDir === 'asc'
      ? <ChevronUp className="h-3 w-3 text-primary-500 shrink-0" />
      : <ChevronDown className="h-3 w-3 text-primary-500 shrink-0" />
  }

  const dash = <span className="text-gray-300 dark:text-gray-600">—</span>
  function cell(v: number | null, dec: number) {
    return v != null ? v.toLocaleString('de-DE', { minimumFractionDigits: dec, maximumFractionDigits: dec }) : dash
  }

  return (
    <Card padding="none" className="overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-gray-200 dark:border-gray-700 flex-wrap">
        <span className="text-xs text-gray-500 dark:text-gray-400">
          Stundenwerte in kW · Σ-Zeile = kWh/Tag
        </span>
        <div className="flex items-center gap-2">
          {/* Spaltenauswahl */}
          <div className="relative" ref={pickerRef}>
            <Button variant="secondary" size="sm" onClick={() => setPickerOpen(o => !o)}>
              <Columns className="h-4 w-4 mr-1.5" />
              Spalten ({visibleCols.size})
            </Button>
            {pickerOpen && (
              <div className="absolute right-0 top-full mt-1 z-20 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-lg p-3 w-56 max-h-96 overflow-y-auto">
                {TD_GROUPS.map(group => {
                  const fixedInGroup = TD_COLUMNS.filter(c => c.group === group)
                  const extraInGroup = group === 'erzeugung' ? extraErzeuger
                    : group === 'verbrauch' ? extraVerbraucher : []
                  const allInGroup = [...fixedInGroup, ...extraInGroup.map(es => ({ key: es.key, label: es.label }))]
                  return (
                    <div key={group} className="mb-3 last:mb-0">
                      <p className="text-[10px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wide mb-1">
                        {TD_GROUP_LABELS[group]}
                      </p>
                      {allInGroup.map(c => (
                        <label key={c.key} className="flex items-center gap-2 py-0.5 cursor-pointer">
                          <input type="checkbox" className="rounded shrink-0"
                            checked={visibleCols.has(c.key)}
                            onChange={() => toggleCol(c.key)} />
                          <span className="text-xs text-gray-700 dark:text-gray-300 truncate">{c.label}</span>
                        </label>
                      ))}
                    </div>
                  )
                })}
                <button type="button"
                  onClick={() => setVisibleCols(new Set(TD_COLUMNS.filter(c => c.defaultVisible).map(c => c.key)))}
                  className="mt-1 w-full text-xs text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 text-center py-1">
                  Standard wiederherstellen
                </button>
              </div>
            )}
          </div>
          <Button variant="secondary" size="sm" onClick={handleExport}>
            <Download className="h-4 w-4 mr-1.5" />
            CSV-Export
          </Button>
        </div>
      </div>

      {/* Tabelle */}
      <div className="overflow-auto max-h-[560px]">
        <table className="w-full text-xs">
          <thead className="sticky top-0 z-10 bg-gray-50 dark:bg-gray-800">
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th
                className="px-3 py-2 text-left font-medium text-gray-500 dark:text-gray-400 whitespace-nowrap cursor-pointer select-none"
                onClick={() => { setSortKey(null); setSortDir('asc') }}
              >
                <span className="flex items-center gap-1">Std {!sortKey && <ChevronUp className="h-3 w-3 text-primary-500" />}</span>
              </th>
              {allCols.map(c => (
                <th key={c.key}
                  className="px-2 py-2 text-right font-medium text-gray-500 dark:text-gray-400 whitespace-nowrap cursor-pointer select-none hover:text-gray-700 dark:hover:text-gray-200"
                  onClick={() => handleSort(c.key)}
                >
                  <span className="flex items-center justify-end gap-1">
                    <SortIcon colKey={c.key} />
                    <span>{c.label}</span>
                  </span>
                  <span className="font-normal text-[10px] opacity-60">{c.unit}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ h, vals }) => (
              <tr key={h} className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/40">
                <td className="px-3 py-1.5 font-medium text-gray-600 dark:text-gray-300 whitespace-nowrap tabular-nums">{h}:00</td>
                {allCols.map(c => (
                  <td key={c.key} className="px-2 py-1.5 text-right tabular-nums text-gray-700 dark:text-gray-300">
                    {cell(vals[c.key], c.decimals)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 font-semibold sticky bottom-0">
              <td className="px-3 py-2 text-gray-500 dark:text-gray-400">Σ kWh</td>
              {allCols.map(c => (
                <td key={c.key} className="px-2 py-2 text-right tabular-nums text-gray-700 dark:text-gray-200">
                  {cell(summen[c.key], c.decimals)}
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
    </Card>
  )
}
