// Energieprofil-Tab — Tagesdetail + Wochenvergleich
// Etappe 2: Auswertung persistierter Stundenwerte aus TagesEnergieProfil
import { useState, useEffect, useMemo, useRef } from 'react'
import {
  ComposedChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import ChartTooltip from '../../components/ui/ChartTooltip'
import { Card, KPICard, ChartLegende } from '../../components/ui'
import { TagVerlaufChart, TagWerteTabelle } from '../../components/tag'
import { energieProfilApi, type StundenWert, type SerieInfo, type WochenmusterPunkt } from '../../api/energie_profil'
import { EnergieprofilMonat } from './EnergieprofilMonat'
import { EnergieprofilPrognose } from './EnergieprofilPrognose'
import {
  DEDIZIERTE_KATEGORIEN, WOCHENTAG_FARBEN,
} from '../../lib'

// ─── Konstanten ───────────────────────────────────────────────────────────────

const WOCHENTAG_KURZ = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

// Gruppierungen für Wochenvergleich
const GRUPPEN = [
  { label: 'Mo–Fr', tage: [0, 1, 2, 3, 4] },
  { label: 'Sa–So', tage: [5, 6] },
  { label: 'Mo', tage: [0] },
  { label: 'Di', tage: [1] },
  { label: 'Mi', tage: [2] },
  { label: 'Do', tage: [3] },
  { label: 'Fr', tage: [4] },
  { label: 'Sa', tage: [5] },
  { label: 'So', tage: [6] },
]

// Tailwind-Klassen für aktive Wochentag-Buttons (kein inline style)
const GRUPPEN_BG_CSS: Record<string, string> = {
  'Mo–Fr': 'bg-blue-500',
  'Sa–So': 'bg-orange-500',
  'Mo':    'bg-indigo-500',
  'Di':    'bg-violet-500',
  'Mi':    'bg-pink-500',
  'Do':    'bg-teal-500',
  'Fr':    'bg-lime-500',
  'Sa':    'bg-amber-500',
  'So':    'bg-red-500',
}

// Zeitraum-Optionen für Wochenvergleich
const ZEITRAUM_OPTIONEN = [
  { label: '30 Tage', tage: 30 },
  { label: '90 Tage', tage: 90 },
  { label: '180 Tage', tage: 180 },
  { label: '365 Tage', tage: 365 },
]

// ─── Helpers ──────────────────────────────────────────────────────────────────

function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10)
}

function gesternISO(): string {
  const d = new Date()
  d.setDate(d.getDate() - 1)
  return toISODate(d)
}

function heuteISO(): string {
  return toISODate(new Date())
}

function vorTagenISO(tage: number): string {
  const d = new Date()
  d.setDate(d.getDate() - tage)
  return toISODate(d)
}

// #181: einen Tag relativ zu einem ISO-Datum verschieben (negativ = zurueck)
function tagVerschieben(isoDatum: string, tage: number): string {
  const d = new Date(isoDatum)
  d.setDate(d.getDate() + tage)
  return toISODate(d)
}

function fmt1(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toFixed(1)
}

function fmt0(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toFixed(0)
}

// ─── Tagesdetail ──────────────────────────────────────────────────────────────

interface TagesdetailProps {
  anlageId: number
}

function Tagesdetail({ anlageId }: TagesdetailProps) {
  const [datum, setDatum] = useState(gesternISO())
  const [daten, setDaten] = useState<StundenWert[]>([])
  const [extraSerien, setExtraSerien] = useState<SerieInfo[]>([])
  const [loading, setLoading] = useState(false)
  // detLAN D#181: Lade…-Indikator nur einblenden, wenn der Fetch laenger als
  // 250ms dauert. Auf schnellen Rechnern → kein Flash; auf langsamen
  // Rechnern / Netzen weiterhin sichtbares Feedback.
  const [zeigeLader, setZeigeLader] = useState(false)

  useEffect(() => {
    if (!anlageId || !datum) return
    setLoading(true)
    energieProfilApi.getStunden(anlageId, datum)
      .then(antwort => {
        setDaten(antwort.stunden)
        setExtraSerien(antwort.serien.filter(s => !DEDIZIERTE_KATEGORIEN.has(s.kategorie)))
      })
      .catch(() => { setDaten([]); setExtraSerien([]) })
      .finally(() => setLoading(false))
  }, [anlageId, datum])

  useEffect(() => {
    if (!loading) {
      setZeigeLader(false)
      return
    }
    const timer = setTimeout(() => setZeigeLader(true), 250)
    return () => clearTimeout(timer)
  }, [loading])

  const extraErzeuger    = extraSerien.filter(s => s.seite === 'quelle')

  // KPIs
  const kpis = useMemo(() => {
    if (!daten.length) return null
    const pvKwh        = daten.reduce((a, d) => a + (d.pv_kw ?? 0), 0)
    const batEntlKwh   = daten.reduce((a, d) => a + Math.max(0, d.batterie_kw ?? 0), 0)
    const erzSonstKwh  = extraErzeuger.reduce((a, es) =>
      a + daten.reduce((b, d) => b + Math.max(0, d.komponenten?.[es.key] ?? 0), 0), 0)
    const gesamterzKwh = pvKwh + batEntlKwh + erzSonstKwh
    const vKwh         = daten.reduce((a, d) => a + (d.verbrauch_kw ?? 0), 0)
    const netzbezugKwh = daten.reduce((a, d) => a + (d.netzbezug_kw ?? 0), 0)
    const einspeisKwh  = daten.reduce((a, d) => a + (d.einspeisung_kw ?? 0), 0)
    const autarkie     = vKwh > 0 ? Math.min(100, (1 - netzbezugKwh / vKwh) * 100) : null
    const temps        = daten.filter(d => d.temperatur_c != null).map(d => d.temperatur_c!)
    return { gesamterzKwh, pvKwh, vKwh, netzbezugKwh, einspeisKwh, autarkie,
             tempMin: temps.length ? Math.min(...temps) : null,
             tempMax: temps.length ? Math.max(...temps) : null }
  }, [daten, extraErzeuger])

  return (
    <div className="space-y-4">
      {/* Datum-Picker mit Vor/Zurueck-Buttons (#181) — analog Monats-Ansicht.
          Maximum ist heute (rollierend via aggregate_today_all geschrieben).
          detLAN D#181: heutiger Tag muss erreichbar sein, war vorher disabled. */}
      <div className="flex items-center gap-2 flex-wrap">
        <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Tag:</label>
        <button
          type="button"
          onClick={() => setDatum(tagVerschieben(datum, -1))}
          className="p-2 rounded-md border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800"
          aria-label="Vorheriger Tag"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <input type="date" aria-label="Tag auswählen" value={datum} max={heuteISO()}
          onChange={e => setDatum(e.target.value)} className="input w-auto text-sm" />
        <button
          type="button"
          onClick={() => setDatum(tagVerschieben(datum, 1))}
          disabled={datum >= heuteISO()}
          className="p-2 rounded-md border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed"
          aria-label="Nächster Tag"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
        {zeigeLader && <span className="text-xs text-gray-400 dark:text-gray-500">Lade…</span>}
      </div>

      {/* KPI-Zeile */}
      {kpis && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
          <KPICard size="sm" title="Verfügbare Energie" value={`${fmt1(kpis.gesamterzKwh)} kWh`} color="yellow" />
          <KPICard size="sm" title="PV-Anteil"       value={`${fmt1(kpis.pvKwh)} kWh`}         color="yellow" />
          <KPICard size="sm" title="Gesamtverbrauch" value={`${fmt1(kpis.vKwh)} kWh`}          color="gray" />
          <KPICard size="sm" title="Netzbezug"       value={`${fmt1(kpis.netzbezugKwh)} kWh`}  color="red" />
          <KPICard size="sm" title="Einspeisung"     value={`${fmt1(kpis.einspeisKwh)} kWh`}   color="blue" />
          <KPICard size="sm" title="Autarkie"        value={kpis.autarkie != null ? `${fmt0(kpis.autarkie)} %` : '—'} color="green" />
          <KPICard size="sm" title="Temperatur"      value={kpis.tempMin != null ? `${fmt1(kpis.tempMin)} / ${fmt1(kpis.tempMax)} °C` : '—'} color="orange" />
        </div>
      )}

      {/* Chart — geteilte SoT-Komponente (Cockpit/Tag + IST) */}
      {daten.length === 0 && !loading ? (
        <Card className="text-center py-10 text-gray-400 dark:text-gray-500 text-sm">
          Keine Daten für diesen Tag vorhanden.
        </Card>
      ) : (
        <TagVerlaufChart daten={daten} extraSerien={extraSerien} />
      )}

      {/* Detailtabelle — geteilte SoT-Komponente */}
      {daten.length > 0 && <TagWerteTabelle daten={daten} extraSerien={extraSerien} datum={datum} />}
    </div>
  )
}

// ─── Wochenvergleich ──────────────────────────────────────────────────────────

interface WochenvergleichProps {
  anlageId: number
}

function Wochenvergleich({ anlageId }: WochenvergleichProps) {
  const [zeitraumTage, setZeitraumTage] = useState(90)
  const [aktivGruppen, setAktivGruppen] = useState<string[]>(['Mo–Fr', 'Sa–So'])
  const [feld, setFeld] = useState<'verbrauch_kw' | 'pv_kw' | 'netzbezug_kw'>('verbrauch_kw')
  const [daten, setDaten] = useState<WochenmusterPunkt[]>([])
  const [loading, setLoading] = useState(false)

  const bis = toISODate(new Date())
  const von = vorTagenISO(zeitraumTage)

  useEffect(() => {
    if (!anlageId) return
    setLoading(true)
    energieProfilApi.getWochenmuster(anlageId, von, bis)
      .then(setDaten)
      .catch(() => setDaten([]))
      .finally(() => setLoading(false))
  }, [anlageId, zeitraumTage])

  // Chart-Daten: eine Zeile pro Stunde, eine Spalte pro aktiver Gruppe
  const chartDaten = useMemo(() => {
    return Array.from({ length: 24 }, (_, h) => {
      const punkt: Record<string, number | string | null> = { stunde: `${h}:00` }
      for (const gruppe of GRUPPEN.filter(g => aktivGruppen.includes(g.label))) {
        const relevant = daten.filter(d => gruppe.tage.includes(d.wochentag) && d.stunde === h)
        if (relevant.length === 0) {
          punkt[gruppe.label] = null
          continue
        }
        const werte = relevant.map(d => d[feld]).filter(v => v != null) as number[]
        punkt[gruppe.label] = werte.length ? round2(werte.reduce((a, b) => a + b, 0) / werte.length) : null
      }
      return punkt
    })
  }, [daten, aktivGruppen, feld])

  function toggleGruppe(label: string) {
    setAktivGruppen(prev =>
      prev.includes(label) ? prev.filter(g => g !== label) : [...prev, label]
    )
  }

  const feldOptionen: { value: typeof feld; label: string }[] = [
    { value: 'verbrauch_kw', label: 'Verbrauch' },
    { value: 'pv_kw', label: 'PV-Erzeugung' },
    { value: 'netzbezug_kw', label: 'Netzbezug' },
  ]

  const anzahlHinweis = useMemo(() => {
    if (!daten.length) return null
    const map = new Map<number, number>()
    for (const d of daten) {
      const prev = map.get(d.wochentag) || 0
      map.set(d.wochentag, Math.max(prev, d.anzahl_tage))
    }
    return map
  }, [daten])

  return (
    <div className="space-y-4">
      {/* Filter-Zeile */}
      <div className="flex flex-wrap items-center gap-4">
        {/* Zeitraum */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Zeitraum:</span>
          <div className="flex gap-1">
            {ZEITRAUM_OPTIONEN.map(o => (
              <button
                type="button"
                key={o.tage}
                onClick={() => setZeitraumTage(o.tage)}
                className={`px-2 py-1 text-xs rounded font-medium transition-colors ${
                  zeitraumTage === o.tage
                    ? 'bg-primary-100 text-primary-700 dark:bg-primary-900 dark:text-primary-300'
                    : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
                }`}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>

        {/* Kennzahl */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Zeige:</span>
          <div className="flex gap-1">
            {feldOptionen.map(o => (
              <button
                type="button"
                key={o.value}
                onClick={() => setFeld(o.value)}
                className={`px-2 py-1 text-xs rounded font-medium transition-colors ${
                  feld === o.value
                    ? 'bg-primary-100 text-primary-700 dark:bg-primary-900 dark:text-primary-300'
                    : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
                }`}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>

        {loading && <span className="text-xs text-gray-400 dark:text-gray-500">Lade…</span>}
      </div>

      {/* Wochentag-Toggles */}
      <div className="flex flex-wrap gap-2">
        {GRUPPEN.map(g => {
          const aktiv = aktivGruppen.includes(g.label)
          const anzahl = g.tage.length === 1 ? anzahlHinweis?.get(g.tage[0]) : null
          return (
            <button
              type="button"
              key={g.label}
              onClick={() => toggleGruppe(g.label)}
              title={anzahl ? `${anzahl} Tage im Zeitraum` : undefined}
              className={`px-3 py-1 text-xs rounded-full font-medium border transition-colors ${
                aktiv
                  ? `border-transparent text-white ${GRUPPEN_BG_CSS[g.label] ?? 'bg-primary-500'}`
                  : 'border-gray-300 dark:border-gray-600 text-gray-500 dark:text-gray-400 bg-transparent'
              }`}
            >
              {g.label}
              {anzahl != null && <span className="ml-1 opacity-70">({anzahl})</span>}
            </button>
          )
        })}
      </div>

      {/* Chart */}
      {daten.length === 0 && !loading ? (
        <Card className="text-center py-10 text-gray-400 dark:text-gray-500 text-sm">
          Keine Daten im gewählten Zeitraum.
        </Card>
      ) : (
        <Card>
          <div className="text-xs text-gray-500 dark:text-gray-400 mb-3">
            Ø-{feldOptionen.find(f => f.value === feld)?.label} in kW je Stunde
            {' '}· Zeitraum: {von} – {bis}
          </div>
          <ResponsiveContainer width="100%" height={320}>
            <ComposedChart data={chartDaten} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(128,128,128,0.15)" />
              <XAxis dataKey="stunde" tick={{ fontSize: 10 }} interval={2} />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={v => `${v}`} />
              <Tooltip content={<ChartTooltip unit=" kW" decimals={2} />} />
              <Legend wrapperStyle={{ fontSize: 12 }} content={<ChartLegende />} />
              {GRUPPEN.filter(g => aktivGruppen.includes(g.label)).map(g => (
                <Line
                  key={g.label}
                  dataKey={g.label}
                  name={g.label}
                  stroke={WOCHENTAG_FARBEN[g.label]}
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                />
              ))}
            </ComposedChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Detailtabelle alle Wochentage × Felder */}
      {daten.length > 0 && <WochenmusterTabelle daten={daten} />}
    </div>
  )
}

// ─── Tabellen ─────────────────────────────────────────────────────────────────


const WM_FELDER = [
  { key: 'pv_kw' as const,          label: 'PV kW',      color: 'text-yellow-600 dark:text-yellow-400' },
  { key: 'verbrauch_kw' as const,    label: 'Verbr. kW',  color: 'text-gray-600 dark:text-gray-300' },
  { key: 'netzbezug_kw' as const,    label: 'Bezug kW',   color: 'text-red-600 dark:text-red-400' },
  { key: 'einspeisung_kw' as const,  label: 'Einsp. kW',  color: 'text-blue-600 dark:text-blue-400' },
  { key: 'batterie_kw' as const,     label: 'Batt. kW',   color: 'text-orange-500 dark:text-orange-400' },
]

function WochenmusterTabelle({ daten }: { daten: WochenmusterPunkt[] }) {
  // Lookup: {wochentag: {stunde: WochenmusterPunkt}}
  const lookup = new Map<number, Map<number, WochenmusterPunkt>>()
  for (const d of daten) {
    if (!lookup.has(d.wochentag)) lookup.set(d.wochentag, new Map())
    lookup.get(d.wochentag)!.set(d.stunde, d)
  }
  const verfuegbareWT = [0,1,2,3,4,5,6].filter(wt => lookup.has(wt))

  return (
    <Card>
      <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-3">
        Ø-Stundenwerte je Wochentag · alle Felder
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th className="text-left py-2 pr-2 font-medium text-gray-500 dark:text-gray-400 sticky left-0 bg-white dark:bg-gray-900">Std</th>
              {verfuegbareWT.map(wt => (
                <th key={wt} colSpan={WM_FELDER.length}
                  className="text-center py-2 px-2 font-medium text-gray-700 dark:text-gray-300 border-l border-gray-200 dark:border-gray-700">
                  {WOCHENTAG_KURZ[wt]}
                </th>
              ))}
            </tr>
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th scope="col" className="sticky left-0 bg-white dark:bg-gray-900">Feld</th>
              {verfuegbareWT.map(wt => (
                WM_FELDER.map(f => (
                  <th key={`${wt}-${f.key}`}
                    className={`text-right py-1 px-1.5 font-normal whitespace-nowrap ${f.color} border-l first:border-l border-gray-100 dark:border-gray-800`}>
                    {f.label.split(' ')[0]}
                  </th>
                ))
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: 24 }, (_, h) => (
              <tr key={h} className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50">
                <td className="py-1.5 pr-2 font-medium text-gray-600 dark:text-gray-300 sticky left-0 bg-white dark:bg-gray-900">{h}:00</td>
                {verfuegbareWT.map(wt => {
                  const p = lookup.get(wt)?.get(h)
                  return WM_FELDER.map(f => {
                    const v = p ? p[f.key] : null
                    return (
                      <td key={`${wt}-${f.key}`}
                        className="text-right py-1.5 px-1.5 tabular-nums text-gray-700 dark:text-gray-300 border-l border-gray-100 dark:border-gray-800">
                        {v != null ? v.toFixed(2) : <span className="text-gray-300 dark:text-gray-600">—</span>}
                      </td>
                    )
                  })
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

// ─── Hilfsfunktionen ──────────────────────────────────────────────────────────

function round2(v: number): number {
  return Math.round(v * 100) / 100
}

// ─── Info-Panel ───────────────────────────────────────────────────────────────

function InfoPanel() {
  const [offen, setOffen] = useState(false)
  const contentRef = useRef<HTMLDivElement>(null)

  return (
    <div className="rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/40">
      <button
        type="button"
        onClick={() => setOffen(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-blue-800 dark:text-blue-300"
      >
        <span className="flex items-center gap-2">
          <span className="text-base">ℹ</span>
          Wie werden die Daten erhoben und verdichtet?
        </span>
        <span className="text-xs opacity-60">{offen ? '▲ schließen' : '▼ anzeigen'}</span>
      </button>

      {offen && (
        <div ref={contentRef} className="px-4 pb-4 text-sm text-blue-900 dark:text-blue-200 space-y-4 border-t border-blue-200 dark:border-blue-800 pt-4">

          <div className="grid sm:grid-cols-2 gap-4">
            <section>
              <h4 className="font-semibold mb-1">Datenquellen</h4>
              <p className="text-xs leading-relaxed opacity-90">
                <strong>HA-App:</strong> Stündliche Mittelwerte aus der Home Assistant Sensor-History.
                HA speichert diese nur ~10 Tage — deshalb werden die Daten täglich persistent in der
                eedc-Datenbank gespeichert.
              </p>
              <p className="text-xs leading-relaxed opacity-90 mt-1">
                <strong>Docker Standalone:</strong> MQTT Live-Snapshots werden alle 5 Minuten in der DB
                gesichert und daraus stündliche Mittelwerte berechnet. Retention: 15 Tage.
              </p>
            </section>

            <section>
              <h4 className="font-semibold mb-1">Aggregations-Zeitplan</h4>
              <ul className="text-xs leading-relaxed opacity-90 space-y-0.5">
                <li><strong>00:15 Uhr täglich</strong> — Vortag wird finalisiert (alle Stunden 0–23)</li>
                <li><strong>alle 15 Min</strong> — laufender Tag rollierend (abgeschlossene Stunden)</li>
                <li><strong>Monatsabschluss</strong> — rückwirkende Nachberechnung falls Lücken</li>
              </ul>
            </section>
          </div>

          <div className="grid sm:grid-cols-2 gap-4">
            <section>
              <h4 className="font-semibold mb-1">Felder erklärt</h4>
              <ul className="text-xs leading-relaxed opacity-90 space-y-0.5">
                <li><strong>PV kW</strong> — Summe aller lokalen Erzeuger (PV-Module, BKW)</li>
                <li><strong>Verbrauch kW</strong> — Gesamtverbrauch (Haushalt + WP + Wallbox + …)</li>
                <li><strong>Bezug / Einspeisung</strong> — Netto-Austausch mit dem Stromnetz</li>
                <li><strong>Batterie kW</strong> — <span className="text-orange-600 dark:text-orange-400 font-medium">positiv = Entladung</span> (Quelle), <span className="text-blue-600 dark:text-blue-400 font-medium">negativ = Ladung</span> (Senke)</li>
                <li><strong>WP / Wallbox kW</strong> — Absolut-Wert des jeweiligen Verbrauchers</li>
                <li><strong>Überschuss kW</strong> — max(0, PV − Verbrauch) je Stunde</li>
                <li><strong>Defizit kW</strong> — max(0, Verbrauch − PV) je Stunde</li>
                <li><strong>SoC %</strong> — Batterie-Ladestand (Stundenmittel)</li>
                <li><strong>Strahlung W/m²</strong> — Globalstrahlung (Open-Meteo Historical)</li>
              </ul>
            </section>

            <section>
              <h4 className="font-semibold mb-1">Wochenvergleich</h4>
              <p className="text-xs leading-relaxed opacity-90">
                Für jeden Wochentag (Mo–So) und jede Stunde wird der <strong>arithmetische
                Mittelwert</strong> aller verfügbaren Tage im gewählten Zeitraum berechnet.
                Die Zahl in Klammern hinter jedem Wochentag-Button zeigt, wie viele Tage
                in die Berechnung einfließen.
              </p>
              <p className="text-xs leading-relaxed opacity-90 mt-1">
                <strong>Empfehlung:</strong> Mindestens 4 Wochen Daten für aussagekräftige Muster.
                Ab 8 Wochen sind saisonale Einflüsse erkennbar.
              </p>
            </section>
          </div>

          <div className="text-xs opacity-70 border-t border-blue-200 dark:border-blue-700 pt-2">
            Summenzeile in der Tagesdetail-Tabelle: kW-Felder aufsummiert ergeben kWh/Tag
            (1 Stundenwert × 1h = kWh). SoC, Temperatur und Strahlung werden nicht summiert.
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Haupt-Tab ────────────────────────────────────────────────────────────────

interface EnergieprofilTabProps {
  anlageId: number
}

const MIN_TAGE = 8  // 1 Woche + 1 Tag

export function EnergieprofilTab({ anlageId }: EnergieprofilTabProps) {
  const [subTab, setSubTab] = useState<'tagesdetail' | 'wochenvergleich' | 'monat' | 'prognose'>('tagesdetail')
  const [tageMitDaten, setTageMitDaten] = useState<number | null>(null)

  // Datenbestand prüfen: letzte 90 Tage abfragen und zählen
  useEffect(() => {
    if (!anlageId) return
    const bis = toISODate(new Date())
    const von = vorTagenISO(90)
    energieProfilApi.getTage(anlageId, von, bis)
      .then(tage => setTageMitDaten(tage.filter(t => t.stunden_verfuegbar > 0).length))
      .catch(() => setTageMitDaten(0))
  }, [anlageId])

  const subTabs = [
    { key: 'tagesdetail' as const, label: 'Tagesdetail' },
    { key: 'wochenvergleich' as const, label: 'Wochenvergleich' },
    { key: 'monat' as const, label: 'Monat' },
    { key: 'prognose' as const, label: 'Prognose' },
  ]

  // Noch nicht genug Daten → Sammelscreen
  // Fortschrittsbalken: 8 mögliche Werte (0–8 Tage), statische Tailwind-Klassen
  const PROGRESS_W = ['w-0','w-[12.5%]','w-1/4','w-[37.5%]','w-1/2','w-[62.5%]','w-3/4','w-[87.5%]','w-full']

  if (tageMitDaten !== null && tageMitDaten < MIN_TAGE) {
    const progressClass = PROGRESS_W[Math.min(tageMitDaten, MIN_TAGE)]
    return (
      <div className="space-y-4">
        <InfoPanel />
        <Card>
          <div className="py-6 text-center space-y-4 max-w-md mx-auto">
            <div className="text-4xl">📊</div>
            <h3 className="text-base font-semibold text-gray-900 dark:text-white">
              Energieprofil sammelt Daten
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Für aussagekräftige Tagesprofile und den Wochenvergleich werden mindestens{' '}
              <strong>{MIN_TAGE} Tage</strong> mit vollständigen Stundenwerten benötigt.
            </p>
            {/* Fortschrittsbalken */}
            <div className="space-y-1">
              <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400">
                <span>{tageMitDaten} von {MIN_TAGE} Tagen</span>
                <span>{Math.round(tageMitDaten / MIN_TAGE * 100)} %</span>
              </div>
              <div className="h-2.5 bg-gray-200 dark:bg-gray-700 rounded-sm overflow-hidden">
                <div className={`h-full bg-primary-500 rounded-sm transition-all ${progressClass}`} />
              </div>
            </div>
            <p className="text-xs text-gray-400 dark:text-gray-500">
              Stundenwerte werden täglich um 00:15 Uhr für den Vortag gespeichert
              und alle 15 Minuten für den laufenden Tag aktualisiert.
            </p>
          </div>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Info-Panel */}
      <InfoPanel />

      {/* Sub-Tab-Navigation — auf Mobile umbrechen, auf Desktop kompakt */}
      <div className="flex flex-wrap gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1 sm:w-fit">
        {subTabs.map(t => (
          <button
            type="button"
            key={t.key}
            onClick={() => setSubTab(t.key)}
            className={`px-3 sm:px-4 py-1.5 text-sm font-medium rounded-md transition-colors flex-1 sm:flex-none ${
              subTab === t.key
                ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {subTab === 'tagesdetail' && <Tagesdetail anlageId={anlageId} />}
      {subTab === 'wochenvergleich' && <Wochenvergleich anlageId={anlageId} />}
      {subTab === 'monat' && <EnergieprofilMonat anlageId={anlageId} />}
      {subTab === 'prognose' && <EnergieprofilPrognose anlageId={anlageId} />}
    </div>
  )
}
