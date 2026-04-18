// Energieprofil-Monat — Heatmap (Tag × Stunde) + KPIs + Peaks
// Etappe 3: Monatsauswertung aus persistierten Stundenwerten
import { useState, useEffect, useMemo } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { Card } from '../../components/ui'
import ChartTooltip from '../../components/ui/ChartTooltip'
import {
  energieProfilApi,
  type MonatsAuswertung, type HeatmapZelle, type PeakStunde,
  type KomponentenEintrag, type KategorieSumme,
} from '../../api/energie_profil'

interface Props {
  anlageId: number
}

type Metrik = 'pv_kw' | 'verbrauch_kw' | 'netzbezug_kw' | 'einspeisung_kw' | 'ueberschuss_kw'

const METRIK_OPTIONEN: { key: Metrik; label: string; farbe: 'green' | 'red' | 'orange' | 'blue' | 'divergent' }[] = [
  { key: 'pv_kw', label: 'PV-Erzeugung', farbe: 'green' },
  { key: 'verbrauch_kw', label: 'Verbrauch', farbe: 'red' },
  { key: 'netzbezug_kw', label: 'Netzbezug', farbe: 'orange' },
  { key: 'einspeisung_kw', label: 'Einspeisung', farbe: 'blue' },
  { key: 'ueberschuss_kw', label: 'Überschuss / Defizit', farbe: 'divergent' },
]

import { MONAT_KURZ, MONAT_NAMEN } from '../../lib/constants'
const MONATSNAMEN = MONAT_KURZ.slice(1)     // 0-basiert
const MONATSNAMEN_LANG = MONAT_NAMEN.slice(1) // 0-basiert

const KATEGORIE_LABEL: Record<string, string> = {
  pv_module: 'PV-Module',
  bkw: 'Balkonkraftwerk',
  sonstige_erzeuger: 'Sonstige Erzeuger',
  waermepumpe: 'Wärmepumpe',
  wallbox_eauto: 'Wallbox / E-Auto',
  haushalt: 'Haushalt',
  sonstige_verbraucher: 'Sonstige Verbraucher',
  speicher: 'Speicher',
  netz: 'Stromnetz',
}

const ERZEUGER_KATS = new Set(['pv_module', 'bkw', 'sonstige_erzeuger'])

function fmt1(v: number | null | undefined, einheit = ''): string {
  if (v == null) return '—'
  return `${v.toFixed(1)}${einheit ? ' ' + einheit : ''}`
}

function fmt0(v: number | null | undefined, einheit = ''): string {
  if (v == null) return '—'
  return `${Math.round(v)}${einheit ? ' ' + einheit : ''}`
}

function gestern(): { jahr: number; monat: number } {
  const d = new Date()
  d.setDate(d.getDate() - 1)
  return { jahr: d.getFullYear(), monat: d.getMonth() + 1 }
}

// Farbe für eine Heatmap-Zelle berechnen
function zellenFarbe(
  wert: number | null | undefined,
  max: number,
  farbe: 'green' | 'red' | 'orange' | 'blue' | 'divergent',
): string {
  if (wert == null) return 'transparent'

  if (farbe === 'divergent') {
    // -max..0..+max → blau (defizit)..weiss..amber (überschuss)
    const norm = Math.max(-1, Math.min(1, wert / max))
    if (norm >= 0) {
      // 0..1 → weiss bis amber-500 (#f59e0b)
      const a = norm.toFixed(2)
      return `rgba(245, 158, 11, ${a})`
    } else {
      const a = (-norm).toFixed(2)
      return `rgba(59, 130, 246, ${a})`
    }
  }

  const norm = Math.max(0, Math.min(1, wert / max))
  if (norm === 0) return 'transparent'
  const a = (norm * 0.95).toFixed(2)
  switch (farbe) {
    case 'green':  return `rgba(16, 185, 129, ${a})`   // emerald-500
    case 'red':    return `rgba(239, 68, 68, ${a})`    // red-500
    case 'orange': return `rgba(249, 115, 22, ${a})`   // orange-500
    case 'blue':   return `rgba(59, 130, 246, ${a})`   // blue-500
    default:       return `rgba(107, 114, 128, ${a})`
  }
}

export function EnergieprofilMonat({ anlageId }: Props) {
  const heute = gestern()
  const [jahr, setJahr] = useState(heute.jahr)
  const [monat, setMonat] = useState(heute.monat)
  const [metrik, setMetrik] = useState<Metrik>('pv_kw')
  const [data, setData] = useState<MonatsAuswertung | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!anlageId) return
    setLoading(true)
    setError(null)
    energieProfilApi.getMonat(anlageId, jahr, monat)
      .then(setData)
      .catch((e) => { setError(String(e?.message ?? e)); setData(null) })
      .finally(() => setLoading(false))
  }, [anlageId, jahr, monat])

  // Heatmap-Lookup: tag → stunde → zelle
  const matrix = useMemo(() => {
    const m: Record<number, Record<number, HeatmapZelle>> = {}
    if (!data) return m
    for (const z of data.heatmap) {
      if (!m[z.tag]) m[z.tag] = {}
      m[z.tag][z.stunde] = z
    }
    return m
  }, [data])

  // Max-Wert für Farbskala der aktuellen Metrik
  const maxWert = useMemo(() => {
    if (!data) return 1
    let max = 0
    for (const z of data.heatmap) {
      const v = z[metrik]
      if (v != null) {
        const abs = Math.abs(v)
        if (abs > max) max = abs
      }
    }
    return max || 1
  }, [data, metrik])

  const monatLabel = `${MONATSNAMEN_LANG[monat - 1]} ${jahr}`
  const farbe = METRIK_OPTIONEN.find(o => o.key === metrik)!.farbe

  const previousMonth = () => {
    if (monat === 1) { setMonat(12); setJahr(jahr - 1) }
    else setMonat(monat - 1)
  }
  const nextMonth = () => {
    if (monat === 12) { setMonat(1); setJahr(jahr + 1) }
    else setMonat(monat + 1)
  }

  // Zukünftige Monate sperren
  const now = new Date()
  const aktJahr = now.getFullYear()
  const aktMonat = now.getMonth() + 1
  const nextDisabled = jahr > aktJahr || (jahr === aktJahr && monat >= aktMonat)

  // Handler, die Zukunfts-Auswahl auf den letzten erlaubten Monat klemmen
  const handleJahrChange = (neuesJahr: number) => {
    setJahr(neuesJahr)
    if (neuesJahr === aktJahr && monat > aktMonat) setMonat(aktMonat)
  }
  const handleMonatChange = (neuerMonat: number) => {
    if (jahr === aktJahr && neuerMonat > aktMonat) setMonat(aktMonat)
    else setMonat(neuerMonat)
  }

  return (
    <div className="space-y-4">
      {/* Monats-Picker */}
      <div className="flex items-center gap-2 flex-wrap">
        <button
          type="button"
          onClick={previousMonth}
          className="p-2 rounded-md border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800"
          aria-label="Vorheriger Monat"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <select
          value={monat}
          onChange={(e) => handleMonatChange(Number(e.target.value))}
          className="input w-auto"
          aria-label="Monat"
        >
          {MONATSNAMEN.map((_, i) => {
            const m = i + 1
            const disabled = jahr === aktJahr && m > aktMonat
            return (
              <option key={m} value={m} disabled={disabled}>{MONATSNAMEN_LANG[i]}</option>
            )
          })}
        </select>
        <select
          value={jahr}
          onChange={(e) => handleJahrChange(Number(e.target.value))}
          className="input w-auto"
          aria-label="Jahr"
        >
          {Array.from({ length: 6 }, (_, i) => aktJahr - i).map(j => (
            <option key={j} value={j}>{j}</option>
          ))}
        </select>
        <button
          type="button"
          onClick={nextMonth}
          disabled={nextDisabled}
          className="p-2 rounded-md border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed"
          aria-label="Nächster Monat"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
        {data && (
          <span className="text-xs text-gray-500 dark:text-gray-400 ml-2">
            {data.tage_mit_daten} von {data.tage_im_monat} Tagen mit Daten
          </span>
        )}
      </div>

      {loading && <Card><div className="py-8 text-center text-sm text-gray-500">Lade Monatsdaten…</div></Card>}
      {error && <Card><div className="py-4 text-center text-sm text-red-600">{error}</div></Card>}

      {data && data.tage_mit_daten === 0 && !loading && (
        <Card>
          <div className="py-8 text-center space-y-2">
            <div className="text-3xl">📅</div>
            <div className="text-sm text-gray-700 dark:text-gray-200">
              Für {monatLabel} liegen keine stündlichen Daten vor.
            </div>
            <div className="text-xs text-gray-500 dark:text-gray-400">
              Im Sensor-Mapping-Wizard kannst du den Verlauf rückwirkend nachberechnen.
            </div>
          </div>
        </Card>
      )}

      {data && data.tage_mit_daten > 0 && (
        <>
          {/* KPI-Strip: Haupt-Kennzahlen */}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
            <KpiCard label="PV-Erzeugung" value={fmt0(data.pv_kwh, 'kWh')} color="text-emerald-600 dark:text-emerald-400" />
            <KpiCard label="Verbrauch" value={fmt0(data.verbrauch_kwh, 'kWh')} color="text-red-600 dark:text-red-400" />
            <KpiCard label="Einspeisung" value={fmt0(data.einspeisung_kwh, 'kWh')} color="text-blue-600 dark:text-blue-400" />
            <KpiCard label="Netzbezug" value={fmt0(data.netzbezug_kwh, 'kWh')} color="text-orange-600 dark:text-orange-400" />
            <KpiCard label="Autarkie" value={data.autarkie_prozent != null ? `${data.autarkie_prozent.toFixed(0)} %` : '—'} />
            <KpiCard label="Eigenverbrauch" value={data.eigenverbrauch_prozent != null ? `${data.eigenverbrauch_prozent.toFixed(0)} %` : '—'} />
            <KpiCard label="PR Ø" value={data.performance_ratio_avg != null ? data.performance_ratio_avg.toFixed(2) : '—'} />
            <KpiCard label="Batterie-Vollzyklen" value={data.batterie_vollzyklen_summe != null ? data.batterie_vollzyklen_summe.toFixed(1) : '—'} />
          </div>

          {/* KPI-Strip: Erweiterte Analyse */}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
            <KpiCard label="Grundbedarf (Nacht)" value={data.grundbedarf_kw != null ? `${data.grundbedarf_kw.toFixed(2)} kW` : '—'} />
            <KpiCard label="Direkt-Eigenverbrauch" value={fmt0(data.direkt_eigenverbrauch_kwh, 'kWh')} color="text-emerald-600 dark:text-emerald-400" />
            <KpiCard label="Batterie geladen" value={fmt0(data.batterie_ladung_kwh, 'kWh')} color="text-blue-600 dark:text-blue-400" />
            <KpiCard label="Batterie entladen" value={fmt0(data.batterie_entladung_kwh, 'kWh')} color="text-orange-600 dark:text-orange-400" />
            <KpiCard label="Batterie-η" value={data.batterie_wirkungsgrad != null ? `${(data.batterie_wirkungsgrad * 100).toFixed(0)} %` : '—'} />
            <KpiCard label="PV Best-Tag" value={fmt0(data.pv_tag_best_kwh, 'kWh')} />
            <KpiCard label="PV Ø-Tag" value={fmt0(data.pv_tag_schnitt_kwh, 'kWh')} />
            <KpiCard label="PV Schlecht-Tag" value={fmt0(data.pv_tag_schlecht_kwh, 'kWh')} />
          </div>

          {/* Börsenpreis / Negativpreis (§51 EEG) — nur wenn Daten vorhanden */}
          {data.negative_preis_stunden != null && data.negative_preis_stunden > 0 && (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              <KpiCard
                label="Neg. Börsenpreis"
                value={`${data.negative_preis_stunden} h`}
                color="text-amber-600 dark:text-amber-400"
              />
              <KpiCard
                label="Einspeisung bei neg. Preis"
                value={fmt1(data.einspeisung_neg_preis_kwh, 'kWh')}
                color="text-amber-600 dark:text-amber-400"
              />
              <KpiCard
                label="Börsenpreis Ø"
                value={data.boersenpreis_avg_cent != null ? `${data.boersenpreis_avg_cent.toFixed(1)} ct` : '—'}
              />
            </div>
          )}

          {/* Kategorien-Leiste */}
          {data.kategorien.length > 0 && (
            <Card>
              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Erzeugung &amp; Verbrauch nach Kategorie</h3>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
                  {data.kategorien.map(k => (
                    <KategorieBadge key={k.kategorie} eintrag={k} />
                  ))}
                </div>
              </div>
            </Card>
          )}

          {/* Geräte-Tabelle */}
          {data.komponenten.length > 0 && (
            <Card>
              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Einzelne Geräte</h3>
                <KomponentenTabelle eintraege={data.komponenten} />
              </div>
            </Card>
          )}

          {/* Typisches Tagesprofil */}
          {data.typisches_tagesprofil.length > 0 && (
            <Card>
              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Typisches Tagesprofil — Ø {monatLabel}</h3>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Stündlicher Mittelwert aus {data.tage_mit_daten} Tagen. Basis für Verbrauchs- und PV-Prognose.
                </p>
                <TagesprofilChart daten={data.typisches_tagesprofil} />
              </div>
            </Card>
          )}

          {/* Heatmap */}
          <Card>
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
                  Heatmap: {METRIK_OPTIONEN.find(o => o.key === metrik)!.label} — {monatLabel}
                </h3>
                <div className="flex flex-wrap gap-1">
                  {METRIK_OPTIONEN.map(opt => (
                    <button
                      type="button"
                      key={opt.key}
                      onClick={() => setMetrik(opt.key)}
                      className={`px-2.5 py-1 text-xs rounded-md border transition-colors ${
                        metrik === opt.key
                          ? 'bg-primary-600 text-white border-primary-600'
                          : 'border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              <Heatmap
                tageImMonat={data.tage_im_monat}
                matrix={matrix}
                metrik={metrik}
                maxWert={maxWert}
                farbe={farbe}
              />

              <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
                <span>Skala 0 → max</span>
                <div className="flex items-center gap-1">
                  {[0, 0.2, 0.4, 0.6, 0.8, 1].map(s => (
                    <div
                      key={s}
                      className="w-5 h-3 rounded-sm border border-gray-200 dark:border-gray-700"
                      style={{ backgroundColor: zellenFarbe(s * maxWert, maxWert, farbe) }}
                    />
                  ))}
                </div>
                <span>0 kW</span>
                <span className="opacity-50">→</span>
                <span>{maxWert.toFixed(1)} kW</span>
              </div>
            </div>
          </Card>

          {/* Peaks */}
          <div className="grid md:grid-cols-2 gap-4">
            <PeakListe
              titel="Top Netzbezug-Stunden"
              hinweis="Spitzenstunden für Tarif-Optimierung"
              eintraege={data.peak_netzbezug}
              farbe="text-orange-600 dark:text-orange-400"
            />
            <PeakListe
              titel="Top Einspeise-Stunden"
              hinweis="PV-Spitzen, ggf. Batterie früher laden"
              eintraege={data.peak_einspeisung}
              farbe="text-blue-600 dark:text-blue-400"
            />
          </div>
        </>
      )}
    </div>
  )
}

// ─── Subkomponenten ──────────────────────────────────────────────────────────

function KpiCard({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 px-3 py-2">
      <div className="text-[11px] text-gray-500 dark:text-gray-400 mb-0.5 truncate">{label}</div>
      <div className={`text-sm font-semibold ${color ?? 'text-gray-900 dark:text-white'}`}>{value}</div>
    </div>
  )
}

interface HeatmapProps {
  tageImMonat: number
  matrix: Record<number, Record<number, HeatmapZelle>>
  metrik: Metrik
  maxWert: number
  farbe: 'green' | 'red' | 'orange' | 'blue' | 'divergent'
}

function Heatmap({ tageImMonat, matrix, metrik, maxWert, farbe }: HeatmapProps) {
  const stunden = Array.from({ length: 24 }, (_, i) => i)
  const tage = Array.from({ length: tageImMonat }, (_, i) => i + 1)

  return (
    <div className="overflow-x-auto">
      <table className="border-separate border-spacing-px text-[10px] select-none">
        <thead>
          <tr>
            <th className="sticky left-0 bg-white dark:bg-gray-900 text-right pr-2 text-gray-500 dark:text-gray-400 font-normal">Tag</th>
            {stunden.map(s => (
              <th key={s} className="w-5 text-center text-gray-500 dark:text-gray-400 font-normal">
                {s % 3 === 0 ? s : ''}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tage.map(tag => (
            <tr key={tag}>
              <td className="sticky left-0 bg-white dark:bg-gray-900 text-right pr-2 text-gray-500 dark:text-gray-400">
                {tag}
              </td>
              {stunden.map(stunde => {
                const zelle = matrix[tag]?.[stunde]
                const wert = zelle ? zelle[metrik] : null
                const bg = zellenFarbe(wert, maxWert, farbe)
                const titel = wert != null
                  ? `Tag ${tag}, ${stunde}:00 — ${wert.toFixed(2)} kW`
                  : `Tag ${tag}, ${stunde}:00 — keine Daten`
                return (
                  <td
                    key={stunde}
                    className="w-5 h-5 border border-gray-100 dark:border-gray-800"
                    style={{ backgroundColor: bg }}
                    title={titel}
                  />
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function KategorieBadge({ eintrag }: { eintrag: KategorieSumme }) {
  const label = KATEGORIE_LABEL[eintrag.kategorie] ?? eintrag.kategorie
  const istErzeuger = ERZEUGER_KATS.has(eintrag.kategorie)
  const farbeClass = istErzeuger
    ? 'text-emerald-700 dark:text-emerald-400'
    : 'text-red-700 dark:text-red-400'
  const bgClass = istErzeuger
    ? 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-900'
    : 'bg-red-50 dark:bg-red-950/40 border-red-200 dark:border-red-900'

  return (
    <div className={`rounded-lg border px-3 py-2 ${bgClass}`}>
      <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate">{label}</div>
      <div className="flex items-baseline justify-between gap-2">
        <span className={`text-sm font-semibold ${farbeClass}`}>
          {Math.round(Math.abs(eintrag.kwh))} kWh
        </span>
        {eintrag.anteil_prozent != null && (
          <span className="text-[11px] text-gray-500 dark:text-gray-400">
            {eintrag.anteil_prozent.toFixed(0)} %
          </span>
        )}
      </div>
    </div>
  )
}

function KomponentenTabelle({ eintraege }: { eintraege: KomponentenEintrag[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
            <th className="text-left font-normal py-1.5">Gerät</th>
            <th className="text-left font-normal py-1.5">Kategorie</th>
            <th className="text-right font-normal py-1.5">kWh</th>
            <th className="text-right font-normal py-1.5">Anteil</th>
          </tr>
        </thead>
        <tbody>
          {eintraege.map((e) => {
            const istErzeuger = e.seite === 'quelle'
            const istBidi = e.seite === 'bidirektional'
            const farbe = istBidi
              ? 'text-gray-600 dark:text-gray-300'
              : istErzeuger
                ? 'text-emerald-600 dark:text-emerald-400'
                : 'text-red-600 dark:text-red-400'
            return (
              <tr key={e.key} className="border-b border-gray-100 dark:border-gray-800 last:border-0">
                <td className="py-1.5 text-gray-800 dark:text-gray-200">{e.label}</td>
                <td className="py-1.5 text-gray-500 dark:text-gray-400">
                  {KATEGORIE_LABEL[e.kategorie] ?? e.kategorie}
                </td>
                <td className={`py-1.5 text-right font-medium ${farbe}`}>
                  {Math.round(Math.abs(e.kwh))}
                </td>
                <td className="py-1.5 text-right text-gray-500 dark:text-gray-400">
                  {e.anteil_prozent != null ? `${e.anteil_prozent.toFixed(0)} %` : '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function TagesprofilChart({ daten }: { daten: { stunde: number; pv_kw: number | null; verbrauch_kw: number | null }[] }) {
  const chartDaten = daten.map(d => ({
    stunde: `${String(d.stunde).padStart(2, '0')}`,
    PV: d.pv_kw,
    Verbrauch: d.verbrauch_kw,
  }))
  return (
    <div style={{ width: '100%', height: 240 }}>
      <ResponsiveContainer>
        <LineChart data={chartDaten} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" strokeOpacity={0.3} />
          <XAxis dataKey="stunde" tick={{ fontSize: 11 }} label={{ value: 'Stunde', position: 'insideBottom', offset: -2, fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} label={{ value: 'kW', angle: -90, position: 'insideLeft', fontSize: 11 }} />
          <Tooltip content={<ChartTooltip unit="kW" />} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line type="monotone" dataKey="PV" stroke="#10b981" strokeWidth={2} dot={false} name="PV Ø" />
          <Line type="monotone" dataKey="Verbrauch" stroke="#ef4444" strokeWidth={2} dot={false} name="Verbrauch Ø" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function PeakListe({ titel, hinweis, eintraege, farbe }: {
  titel: string
  hinweis: string
  eintraege: PeakStunde[]
  farbe: string
}) {
  return (
    <Card>
      <div className="space-y-2">
        <div>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{titel}</h3>
          <p className="text-xs text-gray-500 dark:text-gray-400">{hinweis}</p>
        </div>
        {eintraege.length === 0 ? (
          <div className="py-4 text-center text-xs text-gray-400">Keine Daten</div>
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500 dark:text-gray-400">
                <th className="text-left font-normal pb-1">Datum</th>
                <th className="text-left font-normal pb-1">Stunde</th>
                <th className="text-right font-normal pb-1">Wert</th>
              </tr>
            </thead>
            <tbody>
              {eintraege.map((e, i) => (
                <tr key={i} className="border-t border-gray-100 dark:border-gray-800">
                  <td className="py-1 text-gray-700 dark:text-gray-300">
                    {new Date(e.datum).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })}
                  </td>
                  <td className="py-1 text-gray-700 dark:text-gray-300">{String(e.stunde).padStart(2, '0')}:00</td>
                  <td className={`py-1 text-right font-medium ${farbe}`}>{fmt1(e.wert_kw, 'kW')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Card>
  )
}
