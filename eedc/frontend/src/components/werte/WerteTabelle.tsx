/**
 * WerteTabelle — granularitäts-agnostische Werte-Tabelle (IA v4 Werte-SoT, W2/W3).
 *
 * Zwei Modi:
 *  - `werkbank`: voller Spalten-Picker (Sichtbarkeit + Reihenfolge je Gruppe),
 *    CSV-Export, Vorjahr-Vergleich (aktuell · Vergleich · Δ), Footer-Aggregat.
 *    Persistenz der Picker-Wahl in localStorage. = Auswertungen/Tabelle.
 *  - `embed`: fixer, read-only Spaltensatz (Default Energie-Basis), Footer,
 *    ein Cross-Link „alle Werte / Export →". Für Cockpit-Zeitsichten/Komponenten.
 *
 * Speist sich aus dem W1-Registry (`lib/werte`); Vergleichs-/CSV-/Footer-Logik
 * ist dort zentralisiert (verhaltensgleich aus `TabelleTab` herausgelöst). Die
 * Produktiv-Seite `pages/auswertung/TabelleTab.tsx` bleibt bis zum Flip (3.8)
 * unangetastet — diese Komponente ist der künftige SoT.
 */
import { Fragment, useEffect, useMemo, useState } from 'react'
import { Download, Columns, GitCompareArrows, ChevronUp, ChevronDown, ArrowRight } from 'lucide-react'
import { Button } from '../ui'
import { MONAT_KURZ } from '../../lib'
import type { MonatsZeitreihe } from '../../pages/auswertung/types'
import {
  WERTE_METRIKEN, WERTE_GRUPPEN, GRUPPE_LABELS, METRIK_BY_KEY,
  getMonatWert, fmtWert, aggregiere, bewerteDelta, exportWerteCsv,
  type WerteMetrik,
} from '../../lib/werte'

const LS_COLS = 'eedc-werte-werkbank:cols'
const LS_ORDER = 'eedc-werte-werkbank:order'

const URTEIL_KLASSE: Record<string, string> = {
  gut: 'text-green-600 dark:text-green-400',
  schlecht: 'text-red-500 dark:text-red-400',
  neutral: 'text-gray-400 dark:text-gray-500',
}

function DeltaZelle({ current, prev, metrik }: { current: number | null; prev: number | null; metrik: WerteMetrik }) {
  if (current == null || prev == null) return <span className="text-gray-300 dark:text-gray-600">—</span>
  const delta = current - prev
  const deltaPct = prev !== 0 ? (delta / Math.abs(prev)) * 100 : null
  const urteil = bewerteDelta(current, prev, metrik.higherIsBetter)
  const pfeil = delta > 0 ? '▲' : delta < 0 ? '▼' : '='
  return (
    <span className={URTEIL_KLASSE[urteil]}>
      {pfeil} {fmtWert(Math.abs(delta), metrik.decimals)}
      {deltaPct != null && (
        <span className="ml-1 opacity-75">({deltaPct > 0 ? '+' : ''}{deltaPct.toFixed(1)} %)</span>
      )}
    </span>
  )
}

export interface WerteTabelleProps {
  rows: MonatsZeitreihe[]
  modus: 'werkbank' | 'embed'
  /** Werkbank: Vergleichs-Zeilen (Vorjahr); aktiviert den cur/cmp/Δ-Toggle. */
  vorjahrRows?: MonatsZeitreihe[] | null
  jahrLabel?: string | number
  vergleichLabel?: string | number | null
  /** Embed: fixer Spaltensatz (Default = Energie-Basis). */
  embedKeys?: string[]
  /** Embed: Cross-Link-Ziel „alle Werte / Export →". */
  alleWerteHref?: string
  csvDateiname?: string
}

const EMBED_DEFAULT_KEYS = WERTE_METRIKEN.filter((m) => m.gruppe === 'basis' && m.defaultVisible).map((m) => m.key)

export function WerteTabelle({
  rows,
  modus,
  vorjahrRows = null,
  jahrLabel = '',
  vergleichLabel = null,
  embedKeys,
  alleWerteHref,
  csvDateiname = 'werte_tabelle.csv',
}: WerteTabelleProps) {
  const istEmbed = modus === 'embed'

  // ── Werkbank-State: Sichtbarkeit + Reihenfolge (persistiert) ────────────────
  const [visible, setVisible] = useState<Set<string>>(() => {
    try {
      const raw = localStorage.getItem(LS_COLS)
      if (raw) {
        const keys = (JSON.parse(raw) as string[]).filter((k) => METRIK_BY_KEY[k])
        if (keys.length > 0) return new Set(keys)
      }
    } catch { /* ignore */ }
    return new Set(WERTE_METRIKEN.filter((m) => m.defaultVisible).map((m) => m.key))
  })
  const [order, setOrder] = useState<string[]>(() => {
    try {
      const raw = localStorage.getItem(LS_ORDER)
      if (raw) {
        const keys = JSON.parse(raw) as string[]
        if (WERTE_METRIKEN.every((m) => keys.includes(m.key))) return keys
      }
    } catch { /* ignore */ }
    return WERTE_METRIKEN.map((m) => m.key)
  })
  const [pickerOffen, setPickerOffen] = useState(false)
  const [vergleichAn, setVergleichAn] = useState(false)
  const [showPicker] = useState(modus === 'werkbank')

  useEffect(() => {
    if (istEmbed) return
    try { localStorage.setItem(LS_COLS, JSON.stringify([...visible])) } catch { /* ignore */ }
  }, [visible, istEmbed])
  useEffect(() => {
    if (istEmbed) return
    try { localStorage.setItem(LS_ORDER, JSON.stringify(order)) } catch { /* ignore */ }
  }, [order, istEmbed])

  // ── Aktive Spalten ──────────────────────────────────────────────────────────
  const aktiveMetriken = useMemo<WerteMetrik[]>(() => {
    if (istEmbed) {
      const keys = embedKeys && embedKeys.length > 0 ? embedKeys : EMBED_DEFAULT_KEYS
      return keys.map((k) => METRIK_BY_KEY[k]).filter(Boolean)
    }
    return order.map((k) => METRIK_BY_KEY[k]).filter((m) => m && visible.has(m.key))
  }, [istEmbed, embedKeys, order, visible])

  const vergleichVerfuegbar = !istEmbed && vorjahrRows != null && vorjahrRows.length > 0 && vergleichLabel != null
  const zeigeVergleich = vergleichVerfuegbar && vergleichAn

  const vorjahrLookup = useMemo<Record<number, MonatsZeitreihe>>(() => {
    const m: Record<number, MonatsZeitreihe> = {}
    if (vorjahrRows) for (const r of vorjahrRows) m[r.monat] = r
    return m
  }, [vorjahrRows])

  const aggregat = useMemo(() => aggregiere(rows), [rows])
  const vorjahrAggregat = useMemo(() => (vorjahrRows ? aggregiere(vorjahrRows) : null), [vorjahrRows])

  function verschiebe(key: string, dir: 'up' | 'down') {
    const gruppe = METRIK_BY_KEY[key].gruppe
    const gruppenKeys = WERTE_METRIKEN.filter((m) => m.gruppe === gruppe).map((m) => m.key)
    const inGruppe = order.filter((k) => gruppenKeys.includes(k))
    const idx = inGruppe.indexOf(key)
    const neu = dir === 'up' ? idx - 1 : idx + 1
    if (neu < 0 || neu >= inGruppe.length) return
    const getauscht = [...inGruppe]
    ;[getauscht[idx], getauscht[neu]] = [getauscht[neu], getauscht[idx]]
    setOrder((prev) => {
      const result = [...prev]
      let gi = 0
      for (let i = 0; i < result.length; i++) {
        if (gruppenKeys.includes(result[i])) result[i] = getauscht[gi++]
      }
      return result
    })
  }

  function csvExport() {
    exportWerteCsv({
      rows,
      vorjahrRows: zeigeVergleich ? vorjahrRows : null,
      jahrLabel,
      vergleichLabel: zeigeVergleich ? vergleichLabel : null,
      metriken: aktiveMetriken,
      dateiname: csvDateiname,
    })
  }

  const sorted = useMemo(
    () => [...rows].sort((a, b) => (a.jahr !== b.jahr ? a.jahr - b.jahr : a.monat - b.monat)),
    [rows],
  )

  if (sorted.length === 0) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Werte im Zeitraum.</p>
  }

  return (
    <div className="space-y-3">
      {/* ── Werkbank-Steuerung ─────────────────────────────────────────────── */}
      {showPicker && (
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="secondary" onClick={() => setPickerOffen((o) => !o)}>
            <Columns className="h-4 w-4" /> Spalten
          </Button>
          {vergleichVerfuegbar && (
            <Button
              size="sm"
              variant={zeigeVergleich ? 'primary' : 'secondary'}
              onClick={() => setVergleichAn((v) => !v)}
            >
              <GitCompareArrows className="h-4 w-4" /> Vergleich {vergleichLabel}
            </Button>
          )}
          <Button size="sm" variant="secondary" onClick={csvExport}>
            <Download className="h-4 w-4" /> CSV
          </Button>
        </div>
      )}

      {showPicker && pickerOffen && (
        <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {WERTE_GRUPPEN.map((g) => (
            <div key={g}>
              <p className="text-xs font-semibold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-1">{GRUPPE_LABELS[g]}</p>
              <ul className="space-y-0.5">
                {order.filter((k) => METRIK_BY_KEY[k]?.gruppe === g).map((k) => {
                  const m = METRIK_BY_KEY[k]
                  const an = visible.has(k)
                  return (
                    <li key={k} className="flex items-center gap-1 text-sm">
                      <label className="flex-1 flex items-center gap-2 cursor-pointer min-w-0">
                        <input
                          type="checkbox"
                          checked={an}
                          onChange={() => setVisible((prev) => {
                            const n = new Set(prev)
                            n.has(k) ? n.delete(k) : n.add(k)
                            return n
                          })}
                        />
                        <span className="truncate text-gray-700 dark:text-gray-300">{m.label}</span>
                      </label>
                      <button type="button" aria-label="nach oben" onClick={() => verschiebe(k, 'up')}
                        className="p-1 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
                        <ChevronUp className="h-3.5 w-3.5" />
                      </button>
                      <button type="button" aria-label="nach unten" onClick={() => verschiebe(k, 'down')}
                        className="p-1 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
                        <ChevronDown className="h-3.5 w-3.5" />
                      </button>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </div>
      )}

      {/* ── Tabelle ────────────────────────────────────────────────────────── */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-400 dark:text-gray-500 border-b border-gray-200 dark:border-gray-700">
              <th className="px-3 py-2 font-medium whitespace-nowrap">Zeitraum</th>
              {aktiveMetriken.map((m) => (
                <th key={m.key} colSpan={zeigeVergleich ? 3 : 1} className="px-3 py-2 text-right font-medium whitespace-nowrap">
                  {m.label}{m.unit ? ` (${m.unit})` : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => {
              const prev = zeigeVergleich ? vorjahrLookup[r.monat] : undefined
              return (
                <tr key={`${r.jahr}-${r.monat}`} className="border-b border-gray-100 dark:border-gray-800">
                  <td className="px-3 py-2 whitespace-nowrap text-gray-600 dark:text-gray-400">{MONAT_KURZ[r.monat]} {r.jahr}</td>
                  {aktiveMetriken.map((m) => {
                    const v = getMonatWert(r, m.key)
                    if (zeigeVergleich) {
                      const pv = prev ? getMonatWert(prev, m.key) : null
                      return (
                        <Fragment key={m.key}>
                          <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">{fmtWert(v, m.decimals)}</td>
                          <td className="px-3 py-2 text-right tabular-nums text-gray-500 dark:text-gray-400">{fmtWert(pv, m.decimals)}</td>
                          <td className="px-3 py-2 text-right tabular-nums text-xs border-r border-gray-100 dark:border-gray-800"><DeltaZelle current={v} prev={pv} metrik={m} /></td>
                        </Fragment>
                      )
                    }
                    return <td key={m.key} className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">{fmtWert(v, m.decimals)}</td>
                  })}
                </tr>
              )
            })}
          </tbody>
          {sorted.length > 1 && (
            <tfoot>
              <tr className="border-t-2 border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700/40 font-semibold">
                <td className="px-3 py-2.5 text-gray-600 dark:text-gray-300 text-xs uppercase tracking-wide whitespace-nowrap">
                  {sorted.length} Monate
                </td>
                {aktiveMetriken.map((m) => {
                  const v = aggregat[m.key]
                  const prefix = m.aggregation === 'avg' ? 'Ø ' : ''
                  if (zeigeVergleich) {
                    const pv = vorjahrAggregat?.[m.key] ?? null
                    return (
                      <Fragment key={m.key}>
                        <td className="px-3 py-2.5 text-right tabular-nums text-gray-800 dark:text-gray-100">{v != null ? `${prefix}${fmtWert(v, m.decimals)}` : '—'}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-gray-500 dark:text-gray-400">{pv != null ? `${prefix}${fmtWert(pv, m.decimals)}` : '—'}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-xs border-r border-gray-300 dark:border-gray-600"><DeltaZelle current={v} prev={pv} metrik={m} /></td>
                      </Fragment>
                    )
                  }
                  return <td key={m.key} className="px-3 py-2.5 text-right tabular-nums text-gray-800 dark:text-gray-100">{v != null ? `${prefix}${fmtWert(v, m.decimals)}` : '—'}</td>
                })}
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      {/* ── Embed-Cross-Link „alle Werte / Export →" (W3) ──────────────────── */}
      {istEmbed && alleWerteHref && (
        <a href={alleWerteHref} className="inline-flex items-center gap-1 text-sm text-primary-700 dark:text-primary-300 hover:underline">
          Alle Werte / Export <ArrowRight className="h-4 w-4" />
        </a>
      )}
    </div>
  )
}
