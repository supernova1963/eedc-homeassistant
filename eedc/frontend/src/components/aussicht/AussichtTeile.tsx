/**
 * Aussicht-Präsentationsteile (IA-V4 A.4) — die Vorwärts-Charts/Tabellen/Streifen
 * des Cockpit/Aussicht-Musters, aus den IST-Aussichten-Tabs gezogen, damit
 * Cockpit/Aussicht (v4) und — beim Flip — die Donor-Sichten EINE Code-Wahrheit
 * teilen (Konvergenz-Leitprinzip). Reine Darstellung, kein Daten-Laden, keine
 * Card-Hülle (die `BlockShell`-Sektion rahmt). Farben ausschließlich aus
 * `lib/colors.ts` (kein Inline-Hex, Regel 0a).
 */
import { useState } from 'react'
import {
  Sun, Cloud, CloudSun, CloudRain, CloudSnow, CloudLightning, Thermometer,
  TrendingDown, TrendingUp, Minus, AlertTriangle, ArrowRight,
} from 'lucide-react'
import {
  ResponsiveContainer, ComposedChart, Bar, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from 'recharts'
import ChartTooltip from '../ui/ChartTooltip'
import { fmtCalc, ChartLegende } from '../ui'
import { CHART_COLORS, SOLAR_INTENSITAET, SOLL_IST_COLORS, CHART_HOVER_CURSOR, HILFSLINIE_DASH, KONFIDENZ_BAND_OPACITY, achsenEinheit, achsenTick, ACHSEN_MARGIN_TOP, fmtZahl } from '../../lib'
import { useChartTheme } from '../../context/ThemeContext'
import type { SolarPrognoseTag } from '../../api/wetter'
import type { FinanzPrognose, LangfristPrognose, TrendAnalyseResponse } from '../../api/aussichten'
import type { WaermepumpeDashboardResponse, InvestitionMonatsdaten } from '../../api/investitionen'

// ─── Helfer ──────────────────────────────────────────────────────────────────

export function WetterIcon({ symbol, className = 'h-6 w-6' }: { symbol: string; className?: string }) {
  switch (symbol) {
    case 'sunny': return <Sun className={`${className} text-yellow-500`} />
    case 'mostly_sunny': return <CloudSun className={`${className} text-yellow-400`} />
    case 'partly_cloudy': return <CloudSun className={`${className} text-yellow-300`} />
    case 'cloudy': return <Cloud className={`${className} text-gray-500`} />
    case 'rainy': case 'drizzle': case 'showers': return <CloudRain className={`${className} text-blue-500`} />
    case 'snowy': case 'snow_showers': return <CloudSnow className={`${className} text-blue-300`} />
    case 'thunderstorm': return <CloudLightning className={`${className} text-purple-500`} />
    case 'foggy': return <Cloud className={`${className} text-gray-300`} />
    default: return <Sun className={`${className} text-yellow-400`} />
  }
}

function formatDatum(datum: string): string {
  return new Date(datum).toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit' })
}

// ─── Kurzfristig: Tages-Prognose (Verlauf-Hauptblock) ─────────────────────────
// Merge aus „Prognose-Verlauf" (Tagesbalken) + „Wetter & PV je Tag" (Gernot
// 2026-06-23): EIN spaltengleicher Block — je Tag eine Spalte mit kWh-Wert,
// VM/NM-Balken, Wettersymbol, Temperatur, Datum, exakt untereinander ausgerichtet
// (ein CSS-Grid statt Chart+Streifen, damit die Spalten garantiert fluchten).

const BALKEN_PX = 110 // Höhe der Balken-Spur

export function TagesPrognose({ tage }: { tage: SolarPrognoseTag[] }) {
  const maxKwh = Math.max(...tage.map((t) => t.pv_ertrag_kwh), 0.1)
  const hasVmNm = tage.some((t) => t.pv_ertrag_morgens_kwh != null)
  return (
    <div className="space-y-2">
      {/* Volle Breite: Grid mit gleich breiten Spalten (1fr) füllt den Container;
          minmax(40px,…) lässt es auf schmalen Screens horizontal scrollen. Die
          Säulen wachsen proportional mit (Gernot 2026-06-23). */}
      <div className="overflow-x-auto">
        <div className="grid gap-1" style={{ gridTemplateColumns: `repeat(${tage.length}, minmax(40px, 1fr))` }}>
          {tage.map((tag, index) => {
            const totalPx = (tag.pv_ertrag_kwh / maxKwh) * BALKEN_PX
            const vm = tag.pv_ertrag_morgens_kwh ?? 0
            const nm = tag.pv_ertrag_nachmittags_kwh ?? 0
            const summe = vm + nm
            const vmPx = summe > 0 ? totalPx * (vm / summe) : 0
            const nmPx = summe > 0 ? totalPx * (nm / summe) : 0
            return (
              <div
                key={tag.datum}
                className={`flex flex-col items-center gap-1 rounded-lg px-0.5 pt-1.5 pb-1 ${
                  index === 0 ? 'bg-primary-50 dark:bg-primary-900/30 ring-1 ring-primary-400' : ''
                }`}
              >
                <span className="text-xs font-semibold text-gray-900 dark:text-white tabular-nums">{fmtCalc(tag.pv_ertrag_kwh, 1)}</span>
                <div className="flex flex-col justify-end items-center w-full" style={{ height: BALKEN_PX }}>
                  {hasVmNm && summe > 0 ? (
                    <>
                      <div className="w-1/2 rounded-t" style={{ height: nmPx, backgroundColor: SOLAR_INTENSITAET[1] }} title={`Nachmittag ${fmtCalc(nm, 1)} kWh`} />
                      <div className="w-1/2" style={{ height: vmPx, backgroundColor: SOLAR_INTENSITAET[2] }} title={`Vormittag ${fmtCalc(vm, 1)} kWh`} />
                    </>
                  ) : (
                    <div className="w-1/2 rounded-t" style={{ height: totalPx, backgroundColor: CHART_COLORS.erzeugung }} title={`${fmtCalc(tag.pv_ertrag_kwh, 1)} kWh`} />
                  )}
                </div>
                <WetterIcon symbol={tag.wetter_symbol} className="h-5 w-5" />
                <span className="flex items-center gap-0.5 text-[11px] text-gray-500 dark:text-gray-400">
                  <Thermometer className="h-3 w-3" />{tag.temperatur_max_c != null ? fmtZahl(tag.temperatur_max_c, 0) : '-'}°
                </span>
                <span className="text-[10px] text-gray-400 dark:text-gray-500 text-center leading-tight">{formatDatum(tag.datum)}</span>
              </div>
            )
          })}
        </div>
      </div>
      {hasVmNm && (
        <div className="flex items-center gap-3 text-[11px] text-gray-400 dark:text-gray-500">
          <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded" style={{ backgroundColor: SOLAR_INTENSITAET[2] }} /> Vormittag</span>
          <span className="flex items-center gap-1"><span className="inline-block h-2 w-2 rounded" style={{ backgroundColor: SOLAR_INTENSITAET[1] }} /> Nachmittag</span>
          <span>· Balkenhöhe = PV-Ertrag (kWh)</span>
        </div>
      )}
    </div>
  )
}

// ─── Kurzfristig: Detail-Tabelle (numerischer Zwilling der Tages-Prognose) ─────

// Quellen-Kürzel der Prognose-Kaskade (IST KurzfristTab).
const QUELLEN_KUERZEL: Record<string, { label: string; color: string }> = {
  icon_seamless:       { label: 'ICON-SL', color: 'text-cyan-400' },
  meteoswiss_seamless: { label: 'MS-SL', color: 'text-blue-400' },
  ecmwf_seamless:      { label: 'ECMWF-SL', color: 'text-purple-400' },
  meteoswiss_icon_ch2: { label: 'MeteoSwiss', color: 'text-blue-400' },
  icon_d2:             { label: 'ICON-D2', color: 'text-cyan-400' },
  icon_eu:             { label: 'ICON-EU', color: 'text-green-400' },
  ecmwf_ifs04:         { label: 'ECMWF', color: 'text-purple-400' },
  best_match:          { label: 'Best Match', color: 'text-gray-400 dark:text-gray-500' },
}

/** 14-Tage-Detail-Tabelle (Datum · Wetter · PV · VM/NM · GTI · Bewölkung · Temp ·
 *  Niederschlag · Quelle) — IST KurzfristTab „Details", read-only Werte-Embed. */
export function KurzfristDetails({ tage }: { tage: SolarPrognoseTag[] }) {
  const hasVmNm = tage.some((t) => t.pv_ertrag_morgens_kwh != null)
  const hasKaskade = tage.some((t) => t.datenquelle && t.datenquelle !== 'best_match')
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 dark:border-gray-700 text-xs text-gray-400 dark:text-gray-500">
            <th className="text-left py-2 px-3 font-medium">Datum</th>
            <th className="text-left py-2 px-3 font-medium">Wetter</th>
            <th className="text-right py-2 px-3 font-medium">PV-Prognose</th>
            {hasVmNm && <th className="text-right py-2 px-3 font-medium">VM</th>}
            {hasVmNm && <th className="text-right py-2 px-3 font-medium">NM</th>}
            <th className="text-right py-2 px-3 font-medium">GTI</th>
            <th className="text-right py-2 px-3 font-medium">Bewölkung</th>
            <th className="text-right py-2 px-3 font-medium">Temperatur</th>
            <th className="text-right py-2 px-3 font-medium">Niederschlag</th>
            {hasKaskade && <th className="text-right py-2 px-3 font-medium">Quelle</th>}
          </tr>
        </thead>
        <tbody>
          {tage.map((tag, index) => (
            <tr key={tag.datum} className={`border-b border-gray-100 dark:border-gray-800 ${index === 0 ? 'bg-primary-50 dark:bg-primary-900/20' : ''}`}>
              <td className="py-2 px-3 font-medium">{formatDatum(tag.datum)}</td>
              <td className="py-2 px-3"><WetterIcon symbol={tag.wetter_symbol} className="h-5 w-5" /></td>
              <td className="py-2 px-3 text-right font-semibold text-yellow-600 tabular-nums">{fmtZahl(tag.pv_ertrag_kwh, 1)} kWh</td>
              {hasVmNm && <td className="py-2 px-3 text-right text-amber-500 tabular-nums">{tag.pv_ertrag_morgens_kwh != null ? fmtCalc(tag.pv_ertrag_morgens_kwh, 1) : '-'}</td>}
              {hasVmNm && <td className="py-2 px-3 text-right text-yellow-600 tabular-nums">{tag.pv_ertrag_nachmittags_kwh != null ? fmtCalc(tag.pv_ertrag_nachmittags_kwh, 1) : '-'}</td>}
              <td className="py-2 px-3 text-right tabular-nums">{tag.gti_kwh_m2 != null ? fmtZahl(tag.gti_kwh_m2, 2) : '-'} kWh/m²</td>
              <td className="py-2 px-3 text-right tabular-nums">{tag.bewoelkung_prozent != null ? fmtZahl(tag.bewoelkung_prozent, 0) : '-'} %</td>
              <td className="py-2 px-3 text-right tabular-nums">{tag.temperatur_max_c != null ? fmtZahl(tag.temperatur_max_c, 0) : '-'}°C</td>
              <td className="py-2 px-3 text-right tabular-nums">
                {tag.niederschlag_mm != null && tag.niederschlag_mm > 0
                  ? <span className="text-blue-500">{fmtZahl(tag.niederschlag_mm, 1)} mm</span>
                  : '-'}
              </td>
              {hasKaskade && (
                <td className="py-2 px-3 text-right">
                  <span className={`text-xs font-mono ${QUELLEN_KUERZEL[tag.datenquelle || 'best_match']?.color || 'text-gray-400 dark:text-gray-500'}`}>
                    {QUELLEN_KUERZEL[tag.datenquelle || 'best_match']?.label || tag.datenquelle}
                  </span>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ─── 12 Monate: Verlauf-Hauptblock-Renderer ───────────────────────────────────

/** Monats-Balken PVGIS vs. Trend-korrigiert + Konfidenzband — IST LangfristTab-Chart. */
export function LangfristVerlaufChart({ prognose }: { prognose: LangfristPrognose }) {
  const [showKonfidenz, setShowKonfidenz] = useState(true)
  const achsen = useChartTheme()
  const chartData = prognose.monatswerte.map((m) => ({
    name: `${m.monat_name.substring(0, 3)} ${m.jahr}`,
    pvgis: m.pvgis_prognose_kwh,
    trend: m.trend_korrigiert_kwh,
    konfidenz: [m.konfidenz_min_kwh, m.konfidenz_max_kwh],
  }))
  return (
    <div>
      <label className="flex items-center gap-2 text-sm mb-2 justify-end">
        <input type="checkbox" checked={showKonfidenz} onChange={(e) => setShowKonfidenz(e.target.checked)} className="rounded border-gray-300" />
        <span className="text-gray-600 dark:text-gray-400">Konfidenzband</span>
      </label>
      <div className="h-[350px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: ACHSEN_MARGIN_TOP }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
            <XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-45} textAnchor="end" height={60} className="text-gray-600 dark:text-gray-400" /* achsen-allow: Zeit-/Kategorie-Achse */ />
            <YAxis tick={{ fontSize: 10 }} className="text-gray-600 dark:text-gray-400" tickFormatter={achsenTick} label={achsenEinheit('kWh')} />
            <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip formatter={(value: number, name: string) => {
              if (name === 'Konfidenzband') return null
              return `${fmtCalc(value, 0)} kWh`
            }} />} />
            <Legend content={<ChartLegende />} />
            {showKonfidenz && (
              <Area type="monotone" dataKey="konfidenz" name="Konfidenzband" fill={SOLL_IST_COLORS.soll} fillOpacity={KONFIDENZ_BAND_OPACITY} stroke="none" />
            )}
            {/* PVGIS = Referenz/Basis-Modell, KEINE IST-Serie im Chart (vs. die genauere
                trend-korrigierte Prognose) → HILFSLINIE_DASH statt PROGNOSE_DASH (Regel C). */}
            <Bar dataKey="pvgis" name="PVGIS-Prognose" fill={achsen.referenz} stroke={achsen.referenz} strokeWidth={1} strokeDasharray={HILFSLINIE_DASH} radius={[2, 2, 0, 0]} />
            <Bar dataKey="trend" name="Trend-korrigiert" fill={CHART_COLORS.erzeugung} radius={[2, 2, 0, 0]} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

/** Monatswerte-Tabelle (Monat · PVGIS · Trend-korrigiert · Min · Max · Hist. PR
 *  + Gesamt + Datenquellen) — IST LangfristTab, read-only Werte-Embed. */
export function LangfristMonatswerte({ prognose }: { prognose: LangfristPrognose }) {
  const pr = (v: number | null) =>
    v == null ? <span className="text-gray-400 dark:text-gray-500">-</span>
    : <span className={v > 1 ? 'text-green-600' : v < 0.9 ? 'text-red-600' : 'text-gray-600 dark:text-gray-300'}>{fmtZahl(v * 100, 0)} %</span>
  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-700 text-xs text-gray-400 dark:text-gray-500">
              <th className="text-left py-2 px-3 font-medium">Monat</th>
              <th className="text-right py-2 px-3 font-medium">PVGIS</th>
              <th className="text-right py-2 px-3 font-medium">Trend-korrigiert</th>
              <th className="text-right py-2 px-3 font-medium">Min</th>
              <th className="text-right py-2 px-3 font-medium">Max</th>
              <th className="text-right py-2 px-3 font-medium">Hist. PR</th>
            </tr>
          </thead>
          <tbody>
            {prognose.monatswerte.map((m) => (
              <tr key={`${m.jahr}-${m.monat}`} className="border-b border-gray-100 dark:border-gray-800">
                <td className="py-2 px-3 font-medium">{m.monat_name} {m.jahr}</td>
                <td className="py-2 px-3 text-right text-gray-500 dark:text-gray-400 tabular-nums">{fmtZahl(m.pvgis_prognose_kwh, 0)} kWh</td>
                <td className="py-2 px-3 text-right font-semibold text-yellow-600 tabular-nums">{fmtZahl(m.trend_korrigiert_kwh, 0)} kWh</td>
                <td className="py-2 px-3 text-right text-gray-400 dark:text-gray-500 tabular-nums">{fmtZahl(m.konfidenz_min_kwh, 0)} kWh</td>
                <td className="py-2 px-3 text-right text-gray-400 dark:text-gray-500 tabular-nums">{fmtZahl(m.konfidenz_max_kwh, 0)} kWh</td>
                <td className="py-2 px-3 text-right tabular-nums">{pr(m.historische_performance_ratio)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-gray-300 dark:border-gray-600 font-semibold">
              <td className="py-2 px-3">Gesamt</td>
              <td className="py-2 px-3 text-right text-gray-500 dark:text-gray-400 tabular-nums">{fmtZahl(prognose.monatswerte.reduce((s, m) => s + m.pvgis_prognose_kwh, 0), 0)} kWh</td>
              <td className="py-2 px-3 text-right text-yellow-600 tabular-nums">{prognose.jahresprognose_kwh.toLocaleString('de-DE')} kWh</td>
              <td colSpan={3} />
            </tr>
          </tfoot>
        </table>
      </div>
      {prognose.datenquellen?.length > 0 && (
        <p className="text-xs text-gray-400 dark:text-gray-500">Datenquellen: {prognose.datenquellen.join(', ')}</p>
      )}
    </div>
  )
}

/** Saisonale Muster (beste/schwächste Monate) — IST TrendTab. */
export function SaisonMuster({ muster }: { muster: TrendAnalyseResponse['saisonale_muster'] }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div>
        <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Beste Monate</h4>
        <div className="flex flex-wrap gap-2">
          {muster.beste_monate.map((monat, index) => (
            <span key={monat} className={`px-3 py-1 rounded-full text-sm font-medium ${
              index === 0 ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400' : 'bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-500'
            }`}>{monat}</span>
          ))}
        </div>
      </div>
      <div>
        <h4 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Schwächste Monate</h4>
        <div className="flex flex-wrap gap-2">
          {muster.schlechteste_monate.map((monat, index) => (
            <span key={monat} className={`px-3 py-1 rounded-full text-sm font-medium ${
              index === 0 ? 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400' : 'bg-orange-50 text-orange-700 dark:bg-orange-900/20 dark:text-orange-500'
            }`}>{monat}</span>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Mehrjahr (an 12 M angehängt, AO1): Degradations-PROGNOSE ──────────────────

/** Degradations-Prognose (Vorwärts-Teil aus Trend). Historie → Cockpit/Jahr. */
export function DegradationsPrognose({ trend }: { trend: TrendAnalyseResponse }) {
  const d = trend.degradation
  const grad = d.geschaetzt_prozent_jahr
  return (
    <div className="space-y-3">
      <div className="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
        {grad !== null ? (
          <div className="space-y-2">
            <p className="text-lg font-medium">
              {grad === 0 ? (
                <span className="text-green-600">Keine messbare Degradation</span>
              ) : grad < -1 ? (
                <span className="text-red-600">{fmtZahl(grad, 2)} % pro Jahr</span>
              ) : (
                <span className="text-yellow-600 dark:text-yellow-400">{fmtZahl(grad, 2)} % pro Jahr</span>
              )}
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-400">{d.hinweis}</p>
            {d.methode === 'tmy_ergaenzt' && (
              <p className="text-sm text-blue-600 dark:text-blue-400">Unvollständige Jahre wurden mit PVGIS-TMY-Prognosewerten ergänzt.</p>
            )}
            {d.zuverlaessig === false && (
              <div className="flex items-start gap-1.5 text-sm text-amber-600 dark:text-amber-400">
                <AlertTriangle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                <span>Weniger als 3 vollständige Jahre – Wert ist durch Wetterschwankungen beeinflusst und nur eingeschränkt aussagekräftig.</span>
              </div>
            )}
            {grad < -1 && (
              <p className="text-sm text-yellow-600 dark:text-yellow-400">
                Eine Degradation über 1 % pro Jahr kann auf Probleme hinweisen. Typisch sind 0,3–0,5 % pro Jahr.
              </p>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
            <Minus className="h-4 w-4" />
            <p className="text-sm">{d.hinweis}</p>
          </div>
        )}
      </div>
      <a href="#/v4/cockpit/jahr" className="inline-flex items-center gap-1 text-sm text-primary-700 dark:text-primary-300 hover:underline">
        Jahres-/Mehrjahres-Rückblick (Erträge, PR, Degradations-Analyse) <ArrowRight className="h-4 w-4" />
      </a>
      <p className="text-xs text-gray-400 dark:text-gray-500 flex items-center gap-1">
        <TrendingDown className="h-3 w-3" /> Aussicht zeigt nur die Degradations-Prognose; der historische Rückblick liegt in Cockpit/Jahr.
      </p>
    </div>
  )
}

// ─── Langfristig: WP-Aussicht (data-gated, schlank aus vorhandenen Daten) ──────
// Gernot 2026-06-23: einziger echter Komponenten-Mehrwert. Heimat = Cockpit/
// Aussicht (21.06.-Regel: Komponenten-Temporales → Cockpit/Aussicht), NICHT der
// Hub. Schlank: JAZ-Effizienz-Trend + Ø-Heizsaison-Erwartung aus Historie; voller
// Heizgradtage-Bedarf bleibt späterer Slice. Kosten → Auswertungen.

const HEIZ_MONATE = [10, 11, 12, 1, 2, 3]

function monatsCop(m: InvestitionMonatsdaten): number | null {
  const strom = m.verbrauch_daten.stromverbrauch_kwh || 0
  const waerme = (m.verbrauch_daten.heizenergie_kwh || 0) + (m.verbrauch_daten.warmwasser_kwh || 0)
  return strom > 0 ? waerme / strom : null
}
const mittel = (xs: number[]): number | null => (xs.length ? xs.reduce((s, x) => s + x, 0) / xs.length : null)

function wpTrend(md: InvestitionMonatsdaten[]): { richtung: 'steigend' | 'stabil' | 'sinkend'; recent: number | null; prior: number | null } {
  const cops = md.map(monatsCop).filter((c): c is number => c != null)
  if (cops.length < 4) return { richtung: 'stabil', recent: mittel(cops), prior: null }
  const half = Math.floor(cops.length / 2)
  const prior = mittel(cops.slice(0, half))!
  const recent = mittel(cops.slice(half))!
  const diff = recent - prior
  return { richtung: diff > 0.1 ? 'steigend' : diff < -0.1 ? 'sinkend' : 'stabil', recent, prior }
}

export function WpAussicht({ wpDashboards }: { wpDashboards: WaermepumpeDashboardResponse[] }) {
  return (
    <div className="space-y-3">
      {wpDashboards.map((wp, i) => {
        const z = wp.zusammenfassung
        const md = [...wp.monatsdaten].sort((a, b) => (a.jahr !== b.jahr ? a.jahr - b.jahr : a.monat - b.monat))
        const t = wpTrend(md)
        const heiz = md.filter((m) => HEIZ_MONATE.includes(m.monat))
        const avgStrom = mittel(heiz.map((m) => m.verbrauch_daten.stromverbrauch_kwh || 0))
        const avgWaerme = mittel(heiz.map((m) => (m.verbrauch_daten.heizenergie_kwh || 0) + (m.verbrauch_daten.warmwasser_kwh || 0)))
        const TrendIcon = t.richtung === 'steigend' ? TrendingUp : t.richtung === 'sinkend' ? TrendingDown : Minus
        const trendFarbe = t.richtung === 'steigend' ? 'text-green-600 dark:text-green-400'
          : t.richtung === 'sinkend' ? 'text-red-600 dark:text-red-400' : 'text-gray-500 dark:text-gray-400'
        return (
          <div key={i} className="rounded-lg border border-gray-200 dark:border-gray-700 p-3 space-y-2">
            <p className="font-medium text-gray-900 dark:text-white">{wp.investition.bezeichnung}</p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-gray-500 dark:text-gray-400">Effizienz-Ausblick (JAZ)</p>
                <p className="flex items-center gap-1.5">
                  <span className="font-semibold tabular-nums">{fmtCalc(z.durchschnitt_cop, 2)}</span>
                  <span className={`inline-flex items-center gap-0.5 text-xs ${trendFarbe}`}>
                    <TrendIcon className="h-3.5 w-3.5" /> {t.richtung}
                  </span>
                </p>
                {t.recent != null && t.prior != null && (
                  <p className="text-xs text-gray-400 dark:text-gray-500">zuletzt {fmtZahl(t.recent, 2)} vs. früher {fmtZahl(t.prior, 2)}</p>
                )}
              </div>
              <div>
                <p className="text-gray-500 dark:text-gray-400">Erwartete kommende Heizsaison (Ø)</p>
                {avgStrom != null && avgWaerme != null ? (
                  <p className="tabular-nums">~{fmtZahl(avgStrom * 6, 0)} kWh Strom · ~{fmtZahl(avgWaerme * 6, 0)} kWh Wärme</p>
                ) : <p className="text-gray-400 dark:text-gray-500">noch zu wenig Heizsaison-Daten</p>}
                <p className="text-xs text-gray-400 dark:text-gray-500">Ø aus {heiz.length} erfassten Heizmonaten × 6</p>
              </div>
            </div>
          </div>
        )
      })}
      <a href="#/v4/auswertungen/finanzen" className="inline-flex items-center gap-1 text-sm text-primary-700 dark:text-primary-300 hover:underline">
        WP-Kosten &amp; Ersparnis (Vergleich Gas/Öl) <ArrowRight className="h-4 w-4" />
      </a>
      <p className="text-xs text-gray-400 dark:text-gray-500">
        Schätzung aus historischen Werten · voller Heizgradtage-Bedarf folgt separat.
      </p>
    </div>
  )
}

// ─── Vorwärts-Finanz-Teaser (D2, Gernot 2026-06-23) ──────────────────────────
// Dezenter €-Teaser: Jahres-Netto-Ertrag-Prognose + Aufschlüsselung + Cross-Link.
// Bewusste Lockerung der Spec-F2-a-Linie (Gernot 2026-06-23): EIN schlanker
// Forward-Teaser bleibt in der Aussicht — analog dem Finanz-Teaser in Cockpit/
// Monat (`MonatRahmen.finanzTeaserBlock`). Die volle Finanzrechnung (T-Konto,
// zeitraum-parametrisiert) lebt weiterhin in Auswertungen/Finanzen.
// Zahlen aus `aussichten/finanzen` (Backend-Aggregat, ADR-001) — keine FE-Rechnung.
// `euro` spiegelt bewusst den Monat-Teaser (`+X €` via fmtCalc, mit Vorzeichen),
// damit beide Finanz-Teaser EINE Darstellung teilen (eine Komponenten-Klasse = eine SoT).
export const euroVz = (v: number | null | undefined) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${fmtCalc(v, 2)} €`)

export function AussichtFinanzTeaser({ finanz }: { finanz: FinanzPrognose }) {
  return (
    <div className="space-y-3">
      <dl className="text-sm space-y-1.5">
        <div className="flex justify-between"><dt className="text-gray-500 dark:text-gray-400">Einspeise-Erlös</dt><dd className="tabular-nums text-gray-800 dark:text-gray-200">{euroVz(finanz.jahres_einspeise_erloes_euro)}</dd></div>
        <div className="flex justify-between"><dt className="text-gray-500 dark:text-gray-400">EV-Ersparnis</dt><dd className="tabular-nums text-gray-800 dark:text-gray-200">{euroVz(finanz.jahres_ev_ersparnis_euro)}</dd></div>
        <div className="flex justify-between border-t border-gray-200 dark:border-gray-700 pt-1.5 font-semibold"><dt className="text-gray-700 dark:text-gray-200">Netto-Ertrag (Jahresprognose)</dt><dd className="tabular-nums text-gray-900 dark:text-white">{euroVz(finanz.jahres_netto_ertrag_euro)}</dd></div>
      </dl>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-400 dark:text-gray-500">
        <span>Einspeisung {fmtCalc(finanz.einspeiseverguetung_cent_kwh, 2)} ct/kWh</span>
        <span>Netzbezug {fmtCalc(finanz.netzbezug_preis_cent_kwh, 2)} ct/kWh</span>
      </div>
      <a href="#/v4/auswertungen/finanzen" className="inline-flex items-center gap-1 text-sm text-primary-700 dark:text-primary-300 hover:underline">
        volle Finanzrechnung (T-Konto) <ArrowRight className="h-4 w-4" />
      </a>
      <p className="text-xs text-gray-400 dark:text-gray-500">
        Vorwärts-Schätzung auf Jahresbasis. Das vollständige SOLL/HABEN-T-Konto (zeitraum-parametrisiert) liegt in Auswertungen/Finanzen.
      </p>
    </div>
  )
}
