/**
 * TagWerteTabelle — Stundenwerte-Tabelle eines Tages (24 Zeilen, Σ = kWh/Tag).
 *
 * Aus der IST-„Tagesdetail"-Sicht (`pages/auswertung/EnergieprofilTab.tsx`)
 * extrahiert (hieß dort `TagesdetailTabelle`), damit Cockpit/Tag (v4) und die
 * IST-Seite EINE Code-Wahrheit teilen (Konvergenz). Spalten-Picker (localStorage),
 * Sortierung, CSV-Export, Summenzeile. Reine Darstellung aus `StundenWert[]`.
 */
import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { ChevronUp, ChevronDown, ChevronsUpDown, Columns } from 'lucide-react'
import { Card, Button, CsvExportButton, Table, TableHead, TableBody, TableFoot } from '../ui'
import { ZELLE, KOPF_ZELLE } from '../ui/tabelleMasse'
import { exportToCSV } from '../../utils/export'
import type { StundenWert, SerieInfo } from '../../api/energie_profil'
import { HerkunftZeile } from '../blocks'
import { unvollstaendigHerkunft } from '../../lib/prognoseHinweise'

function round2(v: number): number {
  return Math.round(v * 100) / 100
}

/** Schlüssel der Senken, die `berechneHausverbrauch` abzieht. */
export type SenkenKey = 'waermepumpe_kw' | 'wallbox_kw' | string

/**
 * Welche Senken hat dieser Tag **überhaupt** erfasst?
 *
 * Dieselbe Idee wie `TagesBilanz.*_erfasst` eine Ebene tiefer: *True, sobald EINE
 * Stunde einen Wert trug.* Damit wird trennbar, was am Einzelwert nicht trennbar
 * ist — ein `null` heißt „Gerät gibt es nicht" (nirgends am Tag ein Wert) **oder**
 * „diese Stunde wurde nicht gemessen" (andere Stunden haben Werte). Nur der
 * zweite Fall ist eine Lücke.
 *
 * ⭐ Für die Extra-Senken beantwortet es schon der Vertrag: `serien` wird vom
 * Backend nur befüllt, wenn die Komponente am Tag etwas beigetragen hat
 * (`live_tagesverlauf_service.py`, `if any("…" in p["werte"] …)`). Für die beiden
 * **dedizierten** Felder `waermepumpe_kw`/`wallbox_kw` gibt es keine solche
 * Deklaration — deshalb diese Erhebung über den Tag.
 */
export function erfassteSenken(daten: StundenWert[], extraVerbraucher: SerieInfo[]): Set<SenkenKey> {
  const erfasst = new Set<SenkenKey>()
  if (daten.some((s) => s.waermepumpe_kw != null)) erfasst.add('waermepumpe_kw')
  if (daten.some((s) => s.wallbox_kw != null)) erfasst.add('wallbox_kw')
  for (const es of extraVerbraucher) {
    if (daten.some((s) => s.komponenten?.[es.key] != null)) erfasst.add(es.key)
  }
  return erfasst
}

/**
 * Hausverbrauch einer Stunde = Gesamtverbrauch − Wärmepumpe − Wallbox − sonstige Senken.
 *
 * Eine **Differenz**: fehlt ihr Ausgangswert, ist sie nicht bestimmbar und die Zelle
 * bleibt leer („—"), statt eine Zahl zu behaupten
 * (`docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md` §3 — Differenz ⇒ unterdrücken).
 *
 * Das Backend liefert `verbrauch_kw` bewusst als `null`, solange die Bilanz
 * PV/Einspeisung/Netzbezug nicht vollständig hat (`snapshot/aggregator.py`,
 * `lts_aggregator.py`: „nur wenn pv und einsp und bez"). Der Client machte daraus per
 * `?? 0` eine **0,00** — direkt neben der Spalte „Gesamtverbrauch", die denselben
 * fehlenden Wert als „—" zeigt. Genau dieser Riss war der Befund (PN Rainer 89905).
 *
 * ⭐ **N-95 (29.08.2026): jetzt gelten auch die SUBTRAHENDEN.** §3 Regel 1 wörtlich:
 * *„Eine Differenz erbt die Unvollständigkeit jedes Summanden."* Fehlt einer Senke,
 * die dieser Tag sonst erfasst, der Wert dieser Stunde, dann ist der Hausverbrauch
 * um genau diesen Betrag **zu hoch** — und sah bisher gültig aus. Der Fund nannte
 * das nicht trennbar; trennbar wird es über `erfassteSenken` (s. dort).
 *
 * `erfasst` leer = „keine Senke ist als erfasst bekannt" ⇒ keine Unterdrückung.
 * Das ist die ehrliche Bedeutung eines leeren Sets, kein Rückfall: wer den Tag
 * nicht kennt, kann eine Lücke nicht von einer fehlenden Komponente unterscheiden.
 */
export function berechneHausverbrauch(
  s: StundenWert,
  extraVerbraucher: SerieInfo[],
  erfasst: Set<SenkenKey> = new Set(),
): number | null {
  if (s.verbrauch_kw == null) return null
  if (erfasst.has('waermepumpe_kw') && s.waermepumpe_kw == null) return null
  if (erfasst.has('wallbox_kw') && s.wallbox_kw == null) return null
  let vbrS = 0
  for (const es of extraVerbraucher) {
    const roh = s.komponenten?.[es.key]
    if (roh == null) {
      if (erfasst.has(es.key)) return null
      continue
    }
    vbrS += Math.abs(Math.min(0, roh))
  }
  return round2(Math.max(0, s.verbrauch_kw - (s.waermepumpe_kw ?? 0) - (s.wallbox_kw ?? 0) - vbrS))
}

/**
 * Rohwert einer Komponenten-Serie → **Anzeigewert** für Tabelle, Σ-Zeile und CSV.
 *
 * **Der Befund (N-261).** `TagesEnergieProfil.komponenten` trägt die Vorzeichen-
 * Konvention des **Tagesverlauf-Diagramms**: Quellen nach oben, Senken nach
 * unten, deshalb bekommt jede Senke ein Minus
 * (`live_tagesverlauf_service.py`, `seite === 'senke'` ⇒ `-abs(...)`). Für ein
 * gestapeltes Diagramm ist das richtig. Die Stundentabelle gibt dieselben Werte
 * jedoch **roh** aus — und dort behauptet ein Minus „so viel wurde *nicht*
 * verbraucht". Gemeldet hat es rapahl, ohne es als Fehler zu benennen: Sein
 * Heizstab stand mit **−3,14 / −2,45**, Σ **−5,59 kWh** in der Spalte.
 *
 * Betroffen ist ausschließlich, was **aus `komponenten` kommt** — an der
 * dev-Box gemessen: `sonstige_12` 355 negative Stunden, `waermepumpe_4` 2838,
 * `wallbox_3/5` je 336, während jede Quelle ausnahmslos positiv steht. Die
 * eigenen Spalten (`waermepumpe_kw`, `wallbox_kw`, `verbrauch_kw`) kommen aus
 * dem Zähler-Pfad und waren nie betroffen.
 *
 * ⚠ **`bidirektional` behält sein Vorzeichen** — genau wie die Batterie-Spalte
 * daneben: dort *ist* die Richtung die Aussage (Laden gegen Entladen).
 *
 * ⚠ **Diese Funktion fasst die Arithmetik NICHT an.** `berechneHausverbrauch`
 * oben liest die Rohwerte direkt aus `StundenWert.komponenten` und braucht das
 * Minus (`Math.abs(Math.min(0, …))`). Wer beides zusammenlegt, zieht die
 * Sonstiges-Verbraucher zweimal ab.
 */
export function alsAnzeigewert(roh: number | null | undefined, seite: string): number | null {
  if (roh == null) return null
  return seite === 'senke' ? Math.abs(roh) : roh
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

export function TagWerteTabelle({ daten, extraSerien, erzeugerSerien = [], datum }: {
  daten: StundenWert[]
  extraSerien: SerieInfo[]
  /** PV-Strings/BKW mit eigenem Sensor (#350, Rainer) — je Gerät eine Spalte,
   *  eingehängt hinter „PV". Sie sind bewusst **keine** `extraSerien`: die gehen
   *  in `calcGesamterzeugung` ein, und da die Strings Bestandteile der bereits
   *  gezählten `pv_kw` sind, stünde die Erzeugung dann doppelt in der Bilanz. */
  erzeugerSerien?: SerieInfo[]
  datum: string
}) {
  // Memoisiert → stabile Referenzen (sonst re-rennt jede abhängige useMemo/useCallback je Render).
  const extraErzeuger    = useMemo(() => extraSerien.filter(s => s.seite === 'quelle'), [extraSerien])
  const extraVerbraucher = useMemo(() => extraSerien.filter(s => s.seite === 'senke'), [extraSerien])
  // Ab zwei Geräten — bei einem wäre die Gerätespalte die PV-Spalte (`lib/erzeugerSpalten`).
  const erzeugerSpalten  = useMemo(
    () => (erzeugerSerien.length >= 2 ? erzeugerSerien : []),
    [erzeugerSerien],
  )

  // Berechnete Werte pro Stunde
  const calcGesamterzeugung = useCallback((s: StundenWert): number => {
    const erzS = extraErzeuger.reduce((a, es) => a + Math.max(0, s.komponenten?.[es.key] ?? 0), 0)
    return round2((s.pv_kw ?? 0) + Math.max(0, s.batterie_kw ?? 0) + erzS)
  }, [extraErzeuger])
  // N-95: die Abdeckung des TAGES, einmal erhoben — sie trennt „Gerät gibt es
  // nicht" von „diese Stunde fehlt". Nur mit ihr ist die Differenz unten
  // entscheidbar (`erfassteSenken`).
  const senkenErfasst = useMemo(
    () => erfassteSenken(daten, extraVerbraucher),
    [daten, extraVerbraucher],
  )
  const calcHausverbrauch = useCallback(
    (s: StundenWert) => berechneHausverbrauch(s, extraVerbraucher, senkenErfasst),
    [extraVerbraucher, senkenErfasst],
  )
  // N-94: „Verfügbare Energie" ist eine **additive Summe** — sie wird nach §3
  // BESCHRIFTET, nicht unterdrückt. Fehlen einer erfassten Quelle Stunden, ist
  // die Summe richtungssicher zu niedrig; der Nutzer weiß dann, in welche
  // Richtung er korrigieren muss. Die Zeile ist dieselbe wie im Komponenten-Hub
  // (`HerkunftZeile`, Regel 0a) — keine zweite Bauform für dieselbe Aussage.
  const erzeugungHerkunft = useMemo(() => {
    const luecken: string[] = []
    if (daten.some((s) => s.pv_kw != null) && daten.some((s) => s.pv_kw == null)) luecken.push('PV')
    for (const es of extraErzeuger) {
      const hatWert = daten.some((s) => s.komponenten?.[es.key] != null)
      const hatLuecke = daten.some((s) => s.komponenten?.[es.key] == null)
      if (hatWert && hatLuecke) luecken.push(es.label)
    }
    if (luecken.length === 0) return undefined
    return unvollstaendigHerkunft(
      [
        `Nicht jede Stunde dieses Tages hat einen Messwert (${luecken.join(', ')}). `
        + 'Die Summe „Verfügbare Energie" zählt nur die gemessenen Stunden und ist '
        + 'deshalb zu niedrig — nicht falsch, sondern unvollständig.',
      ],
      'Verfügbare Energie',
    )
  }, [daten, extraErzeuger])

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
    erzeugerSerien.forEach(es => defaults.add(es.key))
    return defaults
  })
  useEffect(() => {
    // Neue extra Serien immer als sichtbar hinzufügen
    setVisibleCols(prev => {
      const next = new Set(prev)
      extraSerien.forEach(es => { if (!next.has(es.key)) next.add(es.key) })
      erzeugerSpalten.forEach(es => { if (!next.has(es.key)) next.add(es.key) })
      return next
    })
  }, [extraSerien, erzeugerSpalten])
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
          // N-261: Senken kommen mit dem Minus des Butterfly-Diagramms herein.
          // `alsAnzeigewert` streift es hier ab — EINE Stelle für Zelle,
          // Σ-Zeile und CSV-Export, die alle drei aus `vals` lesen.
          ...Object.fromEntries(extraSerien.map(es => [es.key, alsAnzeigewert(s?.komponenten?.[es.key], es.seite)])),
          ...Object.fromEntries(erzeugerSpalten.map(es => [es.key, alsAnzeigewert(s?.komponenten?.[es.key], es.seite)])),
        } as Record<string, number | null>,
      }
    })
    if (!sortKey) return all
    return [...all].sort((a, b) => {
      const av = a.vals[sortKey] ?? (sortDir === 'desc' ? -Infinity : Infinity)
      const bv = b.vals[sortKey] ?? (sortDir === 'desc' ? -Infinity : Infinity)
      return sortDir === 'asc' ? av - bv : bv - av
    })
  }, [daten, sortKey, sortDir, extraSerien, erzeugerSpalten, calcGesamterzeugung, calcHausverbrauch])

  // Aktive Spalten in Reihenfolge: TD_COLUMNS + extra Serien (eingebettet in Gruppe)
  const allCols = useMemo(() => {
    const cols: (TdColDef | (SerieInfo & { unit: string; decimals: number; isSum: boolean; group: TdGroup }))[] = []
    for (const c of TD_COLUMNS) {
      cols.push(c)
      // Die Strings stehen direkt hinter ihrer Summe „PV" — sie schlüsseln sie auf.
      if (c.key === 'pv_kw') erzeugerSpalten.forEach(es => cols.push({ ...es, unit: 'kW', decimals: 2, isSum: true, group: 'erzeugung' }))
      if (c.key === 'batterie_kw') extraErzeuger.forEach(es => cols.push({ ...es, unit: 'kW', decimals: 2, isSum: true, group: 'erzeugung' }))
      if (c.key === 'wallbox_kw') extraVerbraucher.forEach(es => cols.push({ ...es, unit: 'kW', decimals: 2, isSum: true, group: 'verbrauch' }))
    }
    return cols.filter(c => visibleCols.has(c.key))
  }, [visibleCols, extraErzeuger, extraVerbraucher, erzeugerSpalten])

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
        <div className="min-w-0">
          <span className="text-xs text-gray-500 dark:text-gray-400">
            Stundenwerte in kW · Σ-Zeile = kWh/Tag
          </span>
          {/* N-94: additive Summe mit Lücke ⇒ beschriften (§3). */}
          {erzeugungHerkunft && <HerkunftZeile herkunft={erzeugungHerkunft} className="mt-1" />}
        </div>
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
          {/* D13-10: Icon + Wort immer, Breakpoint lg (CsvExportButton-SoT). */}
          <CsvExportButton onClick={handleExport} />
        </div>
      </div>

      {/* Tabelle — Zentrale `ui/Table` (Regel T). Vorher: `sticky thead` in einem
          ScrollSchatten OHNE Höhe ⇒ der Kopf klebte nie (der alte Kommentar
          „klebt beim Seiten-Scroll" beruhte auf einer CSS-Fehlannahme: sticky
          haftet am Scroll-Container, nicht am Viewport). Mit dem Höhenfenster
          (24 Zeilen = fachliche Fenstergröße) kleben Kopf UND Summe.
          G16-1 („alle 24 h ohne inneres Scrollen") gilt damit nur noch, solange
          das Fenster unter dem 70dvh-Deckel bleibt — auf flachen Bildschirmen
          scrollt die Tabelle intern. Bewusst abgenommen (Gernot 2026-07-10). */}
      <Table zeilen={24} mitFuss flaeche="karte" className="w-full">
          <TableHead>
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th
                className={`${KOPF_ZELLE} text-left text-gray-500 dark:text-gray-400 cursor-pointer select-none`}
                onClick={() => { setSortKey(null); setSortDir('asc') }}
              >
                <span className="flex items-center gap-1">Std {!sortKey && <ChevronUp className="h-3 w-3 text-primary-500" />}</span>
              </th>
              {allCols.map(c => (
                <th key={c.key}
                  className={`${KOPF_ZELLE} text-right text-gray-500 dark:text-gray-400 cursor-pointer select-none hover:text-gray-700 dark:hover:text-gray-200`}
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
          </TableHead>
          <TableBody>
            {rows.map(({ h, vals }) => (
              <tr key={h} className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/40">
                <td className={`${ZELLE} font-medium text-gray-600 dark:text-gray-300 tabular-nums`}>{h}:00</td>
                {allCols.map(c => (
                  <td key={c.key} className={`${ZELLE} text-right tabular-nums text-gray-700 dark:text-gray-300`}>
                    {cell(vals[c.key], c.decimals)}
                  </td>
                ))}
              </tr>
            ))}
          </TableBody>
          <TableFoot>
            {/* Betonung + deckender Grund kommen aus der Zentrale (FUSS_GRUND). */}
            <tr>
              <td className={`${ZELLE} text-gray-500 dark:text-gray-400`}>Σ kWh</td>
              {allCols.map(c => (
                <td key={c.key} className={`${ZELLE} text-right tabular-nums text-gray-700 dark:text-gray-200`}>
                  {cell(summen[c.key], c.decimals)}
                </td>
              ))}
            </tr>
          </TableFoot>
      </Table>
    </Card>
  )
}
