import { useState, useEffect, useMemo, useCallback } from 'react'
import { Columns, Calendar } from 'lucide-react'
import { Button, Card, Alert, EmptyState } from '../ui'
import { TableHead, TableBody, TableRow, TableHeader, TableCell } from '../ui'
import { DataLoadingState } from '../common'
import { energieProfilApi, type TagesZusammenfassung, type VerfuegbarerMonat } from '../../api/energie_profil'
import { MONAT_KURZ } from '../../lib'

type ColumnGroupKey = 'peaks' | 'summen' | 'performance' | 'wetter' | 'preise'

interface ColumnConfig {
  key: string
  label: string
  group: ColumnGroupKey
  getValue: (t: TagesZusammenfassung) => number | null
  format: 'kwh' | 'kw' | 'percent' | 'temp' | 'zyklen' | 'stunden' | 'ct' | 'int'
  className?: string
  defaultVisible: boolean
}

const COLUMN_GROUPS: Record<ColumnGroupKey, { label: string; color: string }> = {
  peaks:       { label: 'Peak-Leistungen', color: 'bg-blue-500' },
  summen:      { label: 'Tages-Summen',    color: 'bg-amber-500' },
  performance: { label: 'Performance',     color: 'bg-green-500' },
  wetter:      { label: 'Wetter',          color: 'bg-sky-500' },
  preise:      { label: 'Börsenpreis §51', color: 'bg-purple-500' },
}

const COLUMNS: ColumnConfig[] = [
  // Peaks
  { key: 'peak_pv',           label: 'Peak PV',         group: 'peaks',       getValue: (t) => t.peak_pv_kw,           format: 'kw', defaultVisible: true },
  { key: 'peak_netzbezug',    label: 'Peak Netzbezug',  group: 'peaks',       getValue: (t) => t.peak_netzbezug_kw,    format: 'kw', defaultVisible: true },
  { key: 'peak_einspeisung',  label: 'Peak Einspeisung', group: 'peaks',      getValue: (t) => t.peak_einspeisung_kw,  format: 'kw', defaultVisible: true },
  // Tages-Summen
  { key: 'ueberschuss',       label: 'Überschuss',      group: 'summen',      getValue: (t) => t.ueberschuss_kwh,      format: 'kwh', defaultVisible: true },
  { key: 'defizit',           label: 'Defizit',         group: 'summen',      getValue: (t) => t.defizit_kwh,          format: 'kwh', defaultVisible: true },
  // Performance
  { key: 'performance_ratio', label: 'Performance Ratio', group: 'performance', getValue: (t) => t.performance_ratio,  format: 'percent', className: 'text-green-600 dark:text-green-400', defaultVisible: false },
  { key: 'batterie_zyklen',   label: 'Batterie-Zyklen', group: 'performance', getValue: (t) => t.batterie_vollzyklen,  format: 'zyklen', defaultVisible: false },
  { key: 'stunden_verfuegbar',label: 'Stunden verfügbar', group: 'performance', getValue: (t) => t.stunden_verfuegbar, format: 'stunden', defaultVisible: true },
  // Wetter
  { key: 'temp_min',          label: 'Temp. min',       group: 'wetter',      getValue: (t) => t.temperatur_min_c,     format: 'temp', defaultVisible: false },
  { key: 'temp_max',          label: 'Temp. max',       group: 'wetter',      getValue: (t) => t.temperatur_max_c,     format: 'temp', defaultVisible: false },
  { key: 'strahlung',         label: 'Strahlung',       group: 'wetter',      getValue: (t) => t.strahlung_summe_wh_m2 != null ? t.strahlung_summe_wh_m2 / 1000 : null, format: 'kwh', defaultVisible: false },
  // Preise §51
  { key: 'boersen_avg',       label: 'Börsenpreis Ø',   group: 'preise',      getValue: (t) => t.boersenpreis_avg_cent, format: 'ct', defaultVisible: false },
  { key: 'boersen_min',       label: 'Börsenpreis Min', group: 'preise',      getValue: (t) => t.boersenpreis_min_cent, format: 'ct', defaultVisible: false },
  { key: 'neg_preis_stunden', label: 'Negativ-Stunden', group: 'preise',      getValue: (t) => t.negative_preis_stunden, format: 'int', defaultVisible: false },
  { key: 'einsp_neg_preis',   label: 'Einsp. bei neg.', group: 'preise',      getValue: (t) => t.einspeisung_neg_preis_kwh, format: 'kwh', defaultVisible: false },
]

const COLUMNS_STORAGE_KEY = 'eedc-energieprofil-tage-columns-v1'

function formatValue(val: number | null, format: ColumnConfig['format']): string {
  if (val === null || val === undefined || isNaN(val)) return '-'
  switch (format) {
    case 'kwh':     return val.toLocaleString('de-DE', { maximumFractionDigits: 1 })
    case 'kw':      return val.toLocaleString('de-DE', { maximumFractionDigits: 2 })
    case 'percent': return `${(val * 100).toFixed(1)}%`
    case 'temp':    return `${val.toFixed(1)}°C`
    case 'zyklen':  return val.toFixed(2)
    case 'stunden': return `${val}/24`
    case 'ct':      return `${val.toFixed(1)} ct`
    case 'int':     return val.toLocaleString('de-DE')
    default:        return String(val)
  }
}

function monatsBereich(jahr: number, monat: number): { von: string; bis: string } {
  const erster = new Date(jahr, monat - 1, 1)
  const letzter = new Date(jahr, monat, 0)
  const fmt = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  return { von: fmt(erster), bis: fmt(letzter) }
}

interface Props {
  anlageId: number
}

export default function EnergieprofilTageTabelle({ anlageId }: Props) {
  const [verfuegbar, setVerfuegbar] = useState<VerfuegbarerMonat[]>([])
  const [jahr, setJahr] = useState<number | null>(null)
  const [monat, setMonat] = useState<number | null>(null)

  const [daten, setDaten] = useState<TagesZusammenfassung[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showColumnSelector, setShowColumnSelector] = useState(false)

  const [visibleColumns, setVisibleColumns] = useState<Set<string>>(() => {
    try {
      const stored = localStorage.getItem(COLUMNS_STORAGE_KEY)
      if (stored) return new Set(JSON.parse(stored))
    } catch { /* ignore */ }
    return new Set(COLUMNS.filter(c => c.defaultVisible).map(c => c.key))
  })

  useEffect(() => {
    localStorage.setItem(COLUMNS_STORAGE_KEY, JSON.stringify([...visibleColumns]))
  }, [visibleColumns])

  // Verfügbare Monate laden und auf neuesten vorhandenen Monat vorwählen
  useEffect(() => {
    if (!anlageId) return
    let abgebrochen = false
    energieProfilApi.getVerfuegbareMonate(anlageId).then(list => {
      if (abgebrochen) return
      setVerfuegbar(list)
      if (list.length > 0) {
        setJahr(list[0].jahr)
        setMonat(list[0].monat)
      } else {
        setJahr(null)
        setMonat(null)
        setDaten([])
      }
    }).catch(() => {
      if (!abgebrochen) setVerfuegbar([])
    })
    return () => { abgebrochen = true }
  }, [anlageId])

  const load = useCallback(async () => {
    if (!anlageId || jahr == null || monat == null) return
    setLoading(true)
    setError(null)
    try {
      const { von, bis } = monatsBereich(jahr, monat)
      const rows = await energieProfilApi.getTage(anlageId, von, bis)
      rows.sort((a, b) => b.datum.localeCompare(a.datum))
      setDaten(rows)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fehler beim Laden der Tagesdaten')
    } finally {
      setLoading(false)
    }
  }, [anlageId, jahr, monat])

  useEffect(() => { load() }, [load])

  const toggleColumn = (key: string) => {
    setVisibleColumns(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key); else next.add(key)
      return next
    })
  }

  const toggleGroup = (group: ColumnGroupKey) => {
    const groupCols = COLUMNS.filter(c => c.group === group)
    const allVisible = groupCols.every(c => visibleColumns.has(c.key))
    setVisibleColumns(prev => {
      const next = new Set(prev)
      groupCols.forEach(c => { if (allVisible) next.delete(c.key); else next.add(c.key) })
      return next
    })
  }

  const activeColumns = useMemo(() => COLUMNS.filter(c => visibleColumns.has(c.key)), [visibleColumns])

  const jahrOptionen = useMemo(() => {
    return Array.from(new Set(verfuegbar.map(v => v.jahr))).sort((a, b) => b - a)
  }, [verfuegbar])

  const monatOptionen = useMemo(() => {
    if (jahr == null) return []
    return verfuegbar
      .filter(v => v.jahr === jahr)
      .map(v => v.monat)
      .sort((a, b) => b - a)
  }, [verfuegbar, jahr])

  const handleJahrWechsel = (neuesJahr: number) => {
    setJahr(neuesJahr)
    const monateImJahr = verfuegbar.filter(v => v.jahr === neuesJahr).map(v => v.monat)
    if (monat == null || !monateImJahr.includes(monat)) {
      setMonat(monateImJahr.length > 0 ? Math.max(...monateImJahr) : null)
    }
  }

  return (
    <Card>
      <div className="p-6">
        <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
          <div className="flex items-center gap-3">
            <Calendar className="h-6 w-6 text-primary-500" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Tages-Energieprofile
            </h2>
          </div>
          <div className="flex items-center gap-2">
            <label htmlFor="ep-jahr" className="sr-only">Jahr</label>
            <select
              id="ep-jahr"
              value={jahr ?? ''}
              onChange={(e) => handleJahrWechsel(parseInt(e.target.value))}
              disabled={jahrOptionen.length === 0}
              className="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white disabled:opacity-50"
            >
              {jahrOptionen.length === 0 && <option value="">–</option>}
              {jahrOptionen.map(j => <option key={j} value={j}>{j}</option>)}
            </select>
            <label htmlFor="ep-monat" className="sr-only">Monat</label>
            <select
              id="ep-monat"
              value={monat ?? ''}
              onChange={(e) => setMonat(parseInt(e.target.value))}
              disabled={monatOptionen.length === 0}
              className="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 dark:bg-gray-700 dark:border-gray-600 dark:text-white disabled:opacity-50"
            >
              {monatOptionen.length === 0 && <option value="">–</option>}
              {monatOptionen.map(m => (
                <option key={m} value={m}>{MONAT_KURZ[m]}</option>
              ))}
            </select>
            <Button variant="secondary" size="sm" onClick={() => setShowColumnSelector(!showColumnSelector)}>
              <Columns className="h-4 w-4 mr-2" />
              Spalten ({activeColumns.length}/{COLUMNS.length})
            </Button>
          </div>
        </div>

        {error && <Alert type="error">{error}</Alert>}

        {showColumnSelector && (
          <Card className="bg-gray-50 dark:bg-gray-800/50 mb-4">
            <div className="space-y-4">
              {(Object.keys(COLUMN_GROUPS) as ColumnGroupKey[]).map((groupKey) => {
                const group = COLUMN_GROUPS[groupKey]
                const groupColumns = COLUMNS.filter(c => c.group === groupKey)
                const visibleCount = groupColumns.filter(c => visibleColumns.has(c.key)).length
                return (
                  <div key={groupKey}>
                    <div className="flex items-center gap-2 mb-2">
                      <span className={`w-3 h-3 rounded-full ${group.color}`} />
                      <button
                        type="button"
                        onClick={() => toggleGroup(groupKey)}
                        className="text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-primary-600"
                      >
                        {group.label} ({visibleCount}/{groupColumns.length})
                      </button>
                    </div>
                    <div className="flex flex-wrap gap-2 ml-5">
                      {groupColumns.map((col) => (
                        <button
                          type="button"
                          key={col.key}
                          onClick={() => toggleColumn(col.key)}
                          className={`px-3 py-1.5 text-xs font-medium rounded-full transition-colors ${
                            visibleColumns.has(col.key)
                              ? 'bg-primary-500 text-white'
                              : 'bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                          }`}
                        >
                          {col.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-4">
              Klicke auf Gruppen-Namen um alle Spalten ein-/auszublenden, oder auf einzelne Spalten.
            </p>
          </Card>
        )}

        {loading ? (
          <DataLoadingState loading={true} error={null}><div /></DataLoadingState>
        ) : daten.length === 0 ? (
          <EmptyState
            icon={Calendar}
            title={jahr != null && monat != null ? `Keine Tagesdaten für ${MONAT_KURZ[monat]} ${jahr}` : 'Noch keine Tagesdaten'}
            description="Der Scheduler legt pro Tag eine Zusammenfassung an. Falls Daten fehlen, kann der Vollbackfill aus HA-Statistik weiter unten helfen."
          />
        ) : (
          <div className="max-h-[36rem] overflow-auto [&_thead]:sticky [&_thead]:top-0 [&_thead]:z-10 border border-gray-200 dark:border-gray-700 rounded-lg">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <TableHead>
                <TableRow>
                  <TableHeader>Datum</TableHeader>
                  {activeColumns.map((col) => (
                    <TableHeader key={col.key} className="text-right">{col.label}</TableHeader>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {daten.map((t) => (
                  <TableRow key={t.datum}>
                    <TableCell>
                      <span className="font-medium">{t.datum}</span>
                    </TableCell>
                    {activeColumns.map((col) => (
                      <TableCell key={col.key} className={`text-right font-mono ${col.className || ''}`}>
                        {formatValue(col.getValue(t), col.format)}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </table>
          </div>
        )}
      </div>
    </Card>
  )
}
