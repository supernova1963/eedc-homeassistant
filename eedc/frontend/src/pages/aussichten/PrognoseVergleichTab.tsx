/**
 * Prognosen-Vergleich Tab: Evaluierungs-Cockpit für PV-Prognosen
 *
 * Vergleicht OpenMeteo (roh), EEDC (kalibriert), Solcast und IST.
 * - KPI-Matrix: Quellen als Spalten, Zeiträume als Zeilen
 * - Stundenprofil-Chart mit IST, EEDC, Solcast, OpenMeteo
 * - 24h-Vergleichstabelle mit Differenzen
 * - 7-Tage-Vergleichstabelle
 * - Genauigkeits-Tracking + Integrations-Vorschlag
 */
import { useState, useEffect, useRef } from 'react'
import { Sun, CloudSun, Cloud, CloudRain, CloudSnow, CloudLightning, AlertCircle, Info, Zap, BarChart3, Calendar } from 'lucide-react'
import { Card, LoadingSpinner, Alert } from '../../components/ui'
import { SimpleTooltip } from '../../components/ui/FormelTooltip'
import {
  aussichtenApi,
  PrognosenVergleich,
  GenauigkeitsResponse,
  AsymmetrieEintrag,
} from '../../api/aussichten'
import { energieProfilApi } from '../../api/energie_profil'
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from 'recharts'

interface Props {
  anlageId: number
}

function WetterIcon({ symbol, className = "h-5 w-5" }: { symbol: string; className?: string }) {
  switch (symbol) {
    case 'sunny': return <Sun className={`${className} text-yellow-500`} />
    case 'mostly_sunny': return <CloudSun className={`${className} text-yellow-400`} />
    case 'partly_cloudy': return <CloudSun className={`${className} text-yellow-300`} />
    case 'cloudy': return <Cloud className={`${className} text-gray-500`} />
    case 'rainy': case 'drizzle': case 'showers':
      return <CloudRain className={`${className} text-blue-500`} />
    case 'snowy': case 'snow_showers':
      return <CloudSnow className={`${className} text-blue-300`} />
    case 'thunderstorm': return <CloudLightning className={`${className} text-purple-500`} />
    default: return <Sun className={`${className} text-yellow-400`} />
  }
}

function formatDatum(datum: string): string {
  const d = new Date(datum)
  return d.toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit' })
}

/**
 * Datendichte Tabelle nur ab sm-Breakpoint anzeigen, darunter Hinweis.
 * Bewusst pro Tabelle, damit Charts und einfachere Karten auf Mobile sichtbar
 * bleiben. Prognosen-Tab ist Evaluierungsfläche — kein Mobile-Refactor, sondern
 * Hinweis auf passendes Anzeigegerät.
 */
function DatendichtFallback({ children }: { children: React.ReactNode }) {
  return (
    <>
      <div className="hidden sm:block">{children}</div>
      <div className="sm:hidden p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded text-sm text-amber-900 dark:text-amber-200">
        <span className="portrait:inline landscape:hidden">
          Datendichte Tabelle — bitte Gerät ins Querformat drehen oder Desktop verwenden.
        </span>
        <span className="portrait:hidden landscape:inline">
          Auflösung zu gering für datendichte Anzeige — bitte Desktop verwenden.
        </span>
      </div>
    </>
  )
}

function IstUnvollstaendigPopover({
  fehlendeStunden,
  anlageId,
  onReloaded,
}: {
  fehlendeStunden: number[]
  anlageId: number
  onReloaded: () => void
}) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState<{ tone: 'success' | 'warning' | 'error'; msg: string } | null>(null)
  const ref = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const stundenLabel = fehlendeStunden.length === 0
    ? '—'
    : fehlendeStunden.length === 1
      ? `Stunde ${fehlendeStunden[0]}:00–${fehlendeStunden[0] + 1}:00`
      : `Stunden ${fehlendeStunden.map(h => `${h}:00`).join(', ')}`

  const handleReaggregate = async () => {
    setBusy(true)
    setFeedback(null)
    try {
      const heute = new Date().toISOString().slice(0, 10)
      const res = await energieProfilApi.reaggregateTag(anlageId, heute)
      if (res.stunden_mit_messdaten > 0) {
        setFeedback({ tone: 'success', msg: `Neu berechnet: ${res.stunden_mit_messdaten}/24 Stunden mit Daten.` })
      } else {
        setFeedback({ tone: 'warning', msg: 'Reaggregiert, aber HA Statistics liefert noch keine Werte. In ~10 Min erneut versuchen.' })
      }
      onReloaded()
    } catch (e) {
      setFeedback({ tone: 'error', msg: e instanceof Error ? e.message : 'Reaggregation fehlgeschlagen' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <span ref={ref} className="relative inline-block">
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); setOpen(o => !o) }}
        className="ml-1 text-amber-500 hover:text-amber-600 cursor-pointer"
        aria-label="IST-Daten unvollständig"
      >
        ⚠
      </button>
      {open && (
        <div
          className="absolute right-0 top-full mt-1 z-[9999] w-72 max-w-[calc(100vw-2rem)] p-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-xl text-left"
        >
          <div className="text-xs font-semibold text-gray-900 dark:text-white mb-1">
            IST-Daten unvollständig
          </div>
          <div className="text-xs text-gray-600 dark:text-gray-300 leading-relaxed mb-2">
            Ohne Werte für {stundenLabel}.
            Falls EEDC oder HA kürzlich neu gestartet wurden, schließt sich die Lücke
            beim nächsten Snapshot-Zyklus (max. 1 h). Bleibt sie bestehen, ist
            wahrscheinlich der kumulative Zähler im Sensor-Mapping nicht gesetzt.
          </div>
          {feedback && (
            <div className={`text-xs mb-2 px-2 py-1 rounded ${
              feedback.tone === 'success'
                ? 'bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                : feedback.tone === 'warning'
                  ? 'bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300'
                  : 'bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300'
            }`}>
              {feedback.msg}
            </div>
          )}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleReaggregate}
              disabled={busy}
              className="flex-1 px-2 py-1 text-xs font-medium bg-primary-600 hover:bg-primary-700 disabled:bg-gray-400 text-white rounded transition-colors"
            >
              {busy ? 'Berechne…' : 'Tag neu berechnen'}
            </button>
            <a
              href="#/einstellungen/sensor-mapping"
              className="px-2 py-1 text-xs font-medium border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 rounded transition-colors"
            >
              Sensor-Mapping
            </a>
          </div>
        </div>
      )}
    </span>
  )
}

export default function PrognoseVergleichTab({ anlageId }: Props) {
  const [data, setData] = useState<PrognosenVergleich | null>(null)
  const [genauigkeit, setGenauigkeit] = useState<GenauigkeitsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadTick, setReloadTick] = useState(0)
  const [genauigkeitsModus, setGenauigkeitsModus] = useState<'kompakt' | 'diagnostisch'>('kompakt')

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const [prognosen, accuracy] = await Promise.all([
          aussichtenApi.getPrognosenVergleich(anlageId),
          aussichtenApi.getPrognosenGenauigkeit(anlageId, 30).catch(() => null),
        ])
        if (!cancelled) { setData(prognosen); setGenauigkeit(accuracy) }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Fehler beim Laden')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [anlageId, reloadTick])

  if (loading) return <div className="flex justify-center py-12"><LoadingSpinner /></div>
  if (error) return <Alert type="error">{error}</Alert>
  if (!data) return null

  const hasSolcast = data.solcast_verfuegbar
  const hasEedc = data.eedc_lernfaktor !== null || (data.eedc_prognose_basis === 'solcast' && data.eedc_heute_kwh !== null)
  const lf = data.eedc_lernfaktor
  const progBasis = data.eedc_prognose_basis || 'openmeteo'
  const progBasisLabel = progBasis === 'solcast' ? 'Solcast' : 'OpenMeteo'

  // ── Chart-Daten ──
  const chartData = Array.from({ length: 24 }, (_, h) => {
    const om = data.openmeteo_stundenprofil.find(s => s.stunde === h)
    const eedc = data.eedc_stundenprofil.find(s => s.stunde === h)
    const sc = data.solcast_stundenprofil.find(s => s.stunde === h)
    const ist = data.ist_stundenprofil.find(s => s.stunde === h)
    return {
      stunde: `${h}:00`,
      openmeteo: om?.kw ?? 0,
      eedc: eedc?.kw ?? null,
      solcast: sc?.kw ?? 0,
      solcast_p10: sc?.p10_kw ?? 0,
      solcast_p90: sc?.p90_kw ?? 0,
      ist: ist?.kw ?? null,
    }
  })

  // ── 7-Tage-Daten ──
  const heute = new Date().toISOString().slice(0, 10)
  const genauigkeitMap = new Map(
    (genauigkeit?.tage ?? []).map(t => [t.datum, t.ist_kwh])
  )
  const vergleichsTage = data.openmeteo_tage.slice(0, 7).map(om => {
    const sc = data.solcast_tage.find(s => s.datum === om.datum)
    const istKwh = om.datum === heute
      ? data.ist_heute_kwh
      : genauigkeitMap.get(om.datum) ?? null
    return {
      datum: om.datum,
      om_kwh: om.pv_prognose_kwh,
      eedc_kwh: hasEedc ? round(om.pv_prognose_kwh * lf!, 1) : null,
      sc_kwh: sc?.kwh ?? null,
      sc_p10: sc?.p10 ?? null,
      sc_p90: sc?.p90 ?? null,
      wetter_symbol: om.wetter_symbol,
      temp_max: om.temperatur_max_c,
      ist_kwh: istKwh,
    }
  })

  return (
    <div className="space-y-6">
      {/* ── KPI-Matrix ── */}
      <Card>
        <DatendichtFallback>
        <div className="overflow-x-auto">
          <table className="w-full text-sm table-fixed">
            <colgroup>
              <col className="w-32" />
              <col />
              <col />
              {hasSolcast && <col />}
              <col />
            </colgroup>
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="text-left py-2 px-3 font-medium text-gray-500 dark:text-gray-400"></th>
                <th className="text-right py-2 px-3 font-medium text-yellow-500">
                  <SimpleTooltip text="Open-Meteo: GTI-basierte Prognose aus Wettermodell (ICON/ECMWF), 14 Tage Horizont">
                    <span>OpenMeteo</span>
                  </SimpleTooltip>
                </th>
                <th className={`text-right py-2 px-3 font-medium ${hasEedc ? 'text-orange-500' : 'text-gray-400 dark:text-gray-500'}`}>
                  <SimpleTooltip text={hasEedc && lf != null
                    ? `EEDC: ${progBasisLabel} × Lernfaktor ${lf.toFixed(3)} (MOS-kalibriert${data.eedc_lernfaktor_stufe ? ', ' + data.eedc_lernfaktor_stufe : ''})`
                    : `EEDC: Lernfaktor noch nicht verfügbar — siehe Hinweis unten`
                  }>
                    <span>EEDC {hasEedc && lf != null && <span className="text-xs font-normal">×{lf.toFixed(2)}</span>}</span>
                  </SimpleTooltip>
                </th>
                {hasSolcast && (
                  <th className="text-right py-2 px-3 font-medium text-blue-500">
                    <SimpleTooltip text={`Solcast: Satellitenbasierte PV-Prognose mit Konfidenzband, 7 Tage (${data.solcast_quelle === 'solcast_api' ? 'API' : 'HA-Sensor'})`}>
                      <span>Solcast</span>
                    </SimpleTooltip>
                  </th>
                )}
                <th className="text-right py-2 px-3 font-medium text-green-500">
                  <SimpleTooltip text="IST: Tatsächliche PV-Erzeugung aus Sensor-Daten (TagesEnergieProfil)">
                    <span>IST</span>
                  </SimpleTooltip>
                </th>
              </tr>
            </thead>
            <tbody>
              {/* Heute */}
              <tr className="border-b border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/20">
                <td className="py-2 px-3 font-medium text-gray-900 dark:text-white">Heute</td>
                <td className="py-2 px-3 text-right font-mono">{fmtKwh(data.openmeteo_heute_kwh)}</td>
                <td className={`py-2 px-3 text-right font-mono ${hasEedc ? 'font-semibold text-orange-500' : 'text-gray-400'}`}>{hasEedc ? fmtKwh(data.eedc_heute_kwh) : '—'}</td>
                {hasSolcast && <td className="py-2 px-3 text-right font-mono">{fmtKwhBand(data.solcast_heute_kwh, data.solcast_p10_kwh, data.solcast_p90_kwh)}</td>}
                <td className="py-2 px-3 text-right font-mono font-semibold text-green-600 dark:text-green-400">
                  {fmtKwh(data.ist_heute_kwh)}
                  {data.ist_unvollstaendig && (
                    <IstUnvollstaendigPopover
                      fehlendeStunden={data.ist_stundenprofil
                        .filter(s => s.kw === null && s.stunde < new Date().getHours())
                        .map(s => s.stunde)}
                      anlageId={anlageId}
                      onReloaded={() => setReloadTick(t => t + 1)}
                    />
                  )}
                </td>
              </tr>
              {/* Verbleibend */}
              <tr className="border-b border-gray-100 dark:border-gray-800">
                <td className="py-2 px-3 text-gray-500 dark:text-gray-400 text-xs">
                  <SimpleTooltip text="IST bisherig + beste Prognose für verbleibende Stunden (Solcast bevorzugt, sonst EEDC/OpenMeteo)">
                    <span>↳ Verbleibend</span>
                  </SimpleTooltip>
                </td>
                <td className="py-2 px-3 text-right font-mono text-xs text-gray-500">{fmtKwh(data.verbleibend_om_kwh)}</td>
                <td className="py-2 px-3 text-right font-mono text-xs text-gray-500">{hasEedc ? fmtKwh(data.verbleibend_eedc_kwh) : <span className="text-gray-400">—</span>}</td>
                {hasSolcast && <td className="py-2 px-3 text-right font-mono text-xs text-gray-500">{fmtKwh(data.verbleibend_solcast_kwh)}</td>}
                <td className="py-2 px-3 text-right font-mono text-emerald-500">{fmtKwh(data.verbleibend_kwh)}</td>
              </tr>
              {/* VM/NM Heute */}
              <tr className="border-b border-gray-100 dark:border-gray-800">
                <td className="py-1 px-3 text-gray-400 text-xs">↳ VM / NM</td>
                <td className="py-1 px-3 text-right font-mono text-xs text-gray-500">{fmtVmNm(data.openmeteo_tageshaelften?.[0])}</td>
                <td className="py-1 px-3 text-right font-mono text-xs text-gray-500">{hasEedc ? fmtVmNm(data.eedc_tageshaelften?.[0]) : <span className="text-gray-400">—</span>}</td>
                {hasSolcast && <td className="py-1 px-3 text-right font-mono text-xs text-gray-500">{fmtVmNm(data.solcast_tageshaelften?.[0])}</td>}
                <td className="py-1 px-3 text-right font-mono text-xs text-green-500">{fmtVmNm(data.ist_tageshaelfte)}</td>
              </tr>
              {/* Morgen */}
              <tr className="border-b border-gray-100 dark:border-gray-800">
                <td className="py-2 px-3 font-medium text-gray-900 dark:text-white">Morgen</td>
                <td className="py-2 px-3 text-right font-mono">{fmtKwh(data.openmeteo_morgen_kwh)}</td>
                <td className={`py-2 px-3 text-right font-mono ${hasEedc ? 'text-orange-500' : 'text-gray-400'}`}>{hasEedc ? fmtKwh(data.eedc_morgen_kwh) : '—'}</td>
                {hasSolcast && <td className="py-2 px-3 text-right font-mono">{fmtKwhBand(data.solcast_morgen_kwh, data.solcast_morgen_p10_kwh, data.solcast_morgen_p90_kwh)}</td>}
                <td className="py-2 px-3 text-right text-gray-400">—</td>
              </tr>
              {/* VM/NM Morgen */}
              <tr className="border-b border-gray-100 dark:border-gray-800">
                <td className="py-1 px-3 text-gray-400 text-xs">↳ VM / NM</td>
                <td className="py-1 px-3 text-right font-mono text-xs text-gray-500">{fmtVmNm(data.openmeteo_tageshaelften?.[1])}</td>
                <td className="py-1 px-3 text-right font-mono text-xs text-gray-500">{hasEedc ? fmtVmNm(data.eedc_tageshaelften?.[1]) : <span className="text-gray-400">—</span>}</td>
                {hasSolcast && <td className="py-1 px-3 text-right font-mono text-xs text-gray-500">{fmtVmNm(data.solcast_tageshaelften?.[1])}</td>}
                <td className="py-1 px-3"></td>
              </tr>
              {/* Übermorgen */}
              <tr className="border-b border-gray-100 dark:border-gray-800">
                <td className="py-2 px-3 font-medium text-gray-900 dark:text-white">Übermorgen</td>
                <td className="py-2 px-3 text-right font-mono">{fmtKwh(data.openmeteo_uebermorgen_kwh)}</td>
                <td className={`py-2 px-3 text-right font-mono ${hasEedc ? 'text-orange-500' : 'text-gray-400'}`}>{hasEedc ? fmtKwh(data.eedc_uebermorgen_kwh) : '—'}</td>
                {hasSolcast && <td className="py-2 px-3 text-right font-mono">{fmtKwh(data.solcast_uebermorgen_kwh)}</td>}
                <td className="py-2 px-3 text-right text-gray-400">—</td>
              </tr>
              {/* VM/NM Übermorgen */}
              <tr>
                <td className="py-1 px-3 text-gray-400 text-xs">↳ VM / NM</td>
                <td className="py-1 px-3 text-right font-mono text-xs text-gray-500">{fmtVmNm(data.openmeteo_tageshaelften?.[2])}</td>
                <td className="py-1 px-3 text-right font-mono text-xs text-gray-500">{hasEedc ? fmtVmNm(data.eedc_tageshaelften?.[2]) : <span className="text-gray-400">—</span>}</td>
                {hasSolcast && <td className="py-1 px-3 text-right font-mono text-xs text-gray-500">{fmtVmNm(data.solcast_tageshaelften?.[2])}</td>}
                <td className="py-1 px-3"></td>
              </tr>
            </tbody>
          </table>
        </div>
        </DatendichtFallback>
      </Card>

      {/* ── Status-Hinweise ── */}
      {data.solcast_status && data.solcast_status !== 'ok' && data.solcast_hinweis && (
        <Alert type={data.solcast_status === 'tageslimit' ? 'warning' : 'info'}>
          <div className="flex items-start gap-2">
            <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
            <div className="text-sm">{data.solcast_hinweis}</div>
          </div>
        </Alert>
      )}

      {!hasEedc && (() => {
        // Tage mit OpenMeteo-Prognose UND IST (>0.5 kWh) zählen — analog Backend-Filter
        // im _berechne_faktor() (live_wetter.py): nur diese Tage zählen für die 7-Tage-Schwelle.
        const usableDays = (genauigkeit?.tage ?? []).filter(
          t => t.openmeteo_kwh != null && t.openmeteo_kwh > 0 && t.ist_kwh != null && t.ist_kwh > 0.5
        ).length
        const fehlend = Math.max(0, 7 - usableDays)
        return (
          <Alert type="info">
            <div className="flex items-start gap-2">
              <Info className="h-4 w-4 mt-0.5 shrink-0" />
              <div className="text-sm">
                EEDC-Prognose nicht verfügbar — benötigt mindestens 7 Tage mit IST-Ertragsdaten,
                um den Lernfaktor (Verhältnis IST/Prognose) zu berechnen
                {' '}(<strong>{usableDays} von 7 Tagen</strong>{fehlend > 0 ? `, noch ${fehlend} Tag${fehlend === 1 ? '' : 'e'}` : ''}).
                Der Lernfaktor kalibriert die OpenMeteo-Prognose anlagenspezifisch
                und gleicht systematische Abweichungen (Verschattung, Ausrichtung, Alterung) aus.
              </div>
            </div>
          </Alert>
        )
      })()}

      {/* ── Stundenprofil-Chart ── */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Tagesverlauf — Stundenprofil
        </h3>
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.3} />
              <XAxis dataKey="stunde" tick={{ fontSize: 11 }} tickFormatter={(v) => v.replace(':00', '')} />
              <YAxis tick={{ fontSize: 11 }} label={{ value: 'kW', angle: -90, position: 'insideLeft', style: { fontSize: 11 } }} />
              <Tooltip content={<StundenTooltip hasEedc={hasEedc} />} />
              <Legend wrapperStyle={{ fontSize: 12 }} formatter={(v: string) => ({
                ist: 'IST', eedc: `EEDC${lf != null ? ` (${progBasisLabel} ×${lf.toFixed(2)})` : ''}`, solcast: 'Solcast', openmeteo: 'OpenMeteo (roh)'
              }[v] || v)} />
              {data.aktuelle_stunde !== null && (
                <ReferenceLine x={`${data.aktuelle_stunde}:00`} stroke="#6b7280" strokeDasharray="3 3"
                  label={{ value: 'Jetzt', position: 'top', fontSize: 10, fill: '#9ca3af' }} />
              )}
              <Area dataKey="ist" stroke="#22c55e" fill="#22c55e" fillOpacity={0.3} strokeWidth={2} dot={false} name="ist" connectNulls={false} />
              {hasSolcast && <Line dataKey="solcast" stroke="#3b82f6" strokeWidth={2} dot={false} name="solcast" />}
              {hasEedc && <Line dataKey="eedc" stroke="#f97316" strokeWidth={2} dot={false} name="eedc" />}
              <Line dataKey="openmeteo" stroke="#eab308" strokeWidth={1.5} strokeDasharray="5 3" dot={false} name="openmeteo" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* ── 24-Stunden-Vergleichstabelle ── */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Stundenvergleich heute
        </h3>
        <div>
          <table className="w-full text-xs table-fixed">
            <colgroup>
              <col className="w-16" />
              <col />
              <col />
              {hasSolcast && <col />}
              <col />
            </colgroup>
            <thead className="bg-white dark:bg-gray-900">
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="text-left py-1.5 px-2 font-medium text-gray-500">Std.</th>
                <th className="text-right py-1.5 px-2 font-medium text-yellow-500">OM</th>
                <th className={`text-right py-1.5 px-2 font-medium ${hasEedc ? 'text-orange-500' : 'text-gray-400'}`}>EEDC</th>
                {hasSolcast && <th className="text-right py-1.5 px-2 font-medium text-blue-500">SC</th>}
                <th className="text-right py-1.5 pl-2 pr-3 font-medium text-green-500">IST</th>
              </tr>
            </thead>
            <tbody>
              {chartData.filter(r => r.openmeteo > 0.01 || r.solcast > 0.01 || (r.ist !== null && r.ist > 0.01)).map((row) => {
                const h = parseInt(row.stunde)
                const isPast = data.aktuelle_stunde !== null && h <= data.aktuelle_stunde
                const istVal = row.ist
                return (
                  <tr key={row.stunde} className={`border-b border-gray-50 dark:border-gray-800 ${isPast ? 'bg-gray-50/50 dark:bg-gray-800/30' : ''}`}>
                    <td className="py-1 px-2 font-mono text-gray-900 dark:text-white">{row.stunde}</td>
                    <td className="py-1 px-2 text-right font-mono">
                      {row.openmeteo.toFixed(2)}
                      {istVal !== null && <DevBadge prognose={row.openmeteo} ist={istVal} />}
                    </td>
                    <td className={`py-1 px-2 text-right font-mono ${hasEedc ? 'text-orange-500' : 'text-gray-400'}`}>
                      {hasEedc ? (
                        <>
                          {row.eedc?.toFixed(2) ?? '—'}
                          {istVal !== null && row.eedc !== null && <DevBadge prognose={row.eedc} ist={istVal} />}
                        </>
                      ) : '—'}
                    </td>
                    {hasSolcast && (
                      <td className="py-1 px-2 text-right font-mono">
                        {row.solcast.toFixed(2)}
                        {istVal !== null && <DevBadge prognose={row.solcast} ist={istVal} />}
                      </td>
                    )}
                    <td className="py-1 pl-2 pr-3 text-right font-mono font-semibold text-green-600 dark:text-green-400">
                      {istVal !== null ? istVal.toFixed(2) : <span className="text-gray-400">—</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
            <tfoot className="bg-white dark:bg-gray-900">
              {(() => {
                const omSum = chartData.reduce((s, r) => s + r.openmeteo, 0)
                const eedcSum = chartData.reduce((s, r) => s + (r.eedc ?? 0), 0)
                const scSum = chartData.reduce((s, r) => s + r.solcast, 0)
                const istSum = data.ist_heute_kwh
                return (
                  <tr className="border-t-2 border-gray-300 dark:border-gray-600 font-semibold">
                    <td className="py-1.5 px-2 text-gray-900 dark:text-white">Σ</td>
                    <td className="py-1.5 px-2 text-right font-mono text-yellow-500">
                      {omSum.toFixed(1)}
                      {istSum !== null && <DevBadge prognose={omSum} ist={istSum} />}
                    </td>
                    <td className={`py-1.5 px-2 text-right font-mono ${hasEedc ? 'text-orange-500' : 'text-gray-400'}`}>
                      {hasEedc ? (
                        <>
                          {eedcSum.toFixed(1)}
                          {istSum !== null && <DevBadge prognose={eedcSum} ist={istSum} />}
                        </>
                      ) : '—'}
                    </td>
                    {hasSolcast && (
                      <td className="py-1.5 px-2 text-right font-mono text-blue-500">
                        {scSum.toFixed(1)}
                        {istSum !== null && <DevBadge prognose={scSum} ist={istSum} />}
                      </td>
                    )}
                    <td className="py-1.5 pl-2 pr-3 text-right font-mono text-green-500">{istSum !== null ? istSum.toFixed(1) : '—'}</td>
                  </tr>
                )
              })()}
            </tfoot>
          </table>
        </div>
      </Card>

      {/* ── 7-Tage-Vergleichstabelle ── */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">7-Tage-Vergleich</h3>
        <DatendichtFallback>
        <div className="overflow-x-auto">
          <table className="w-full text-sm table-fixed">
            <colgroup>
              <col className="w-20" />
              <col className="w-24" />
              <col />
              <col />
              {hasSolcast && <col />}
              <col />
            </colgroup>
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="py-2 px-2" aria-label="Wetter"></th>
                <th className="text-left py-2 px-2 font-medium text-gray-500">Datum</th>
                <th className="text-right py-2 px-2 font-medium text-yellow-500">OM</th>
                <th className={`text-right py-2 px-2 font-medium ${hasEedc ? 'text-orange-500' : 'text-gray-400'}`}>EEDC</th>
                {hasSolcast && <th className="text-right py-2 px-2 font-medium text-blue-500">Solcast</th>}
                <th className="text-right py-2 pl-2 pr-3 font-medium text-green-500">IST</th>
              </tr>
            </thead>
            <tbody>
              {vergleichsTage.map((tag) => {
                // Referenz: IST wenn vorhanden, sonst Mittelwert aller Prognosen
                const ref = tag.ist_kwh
                const prognosen = [tag.om_kwh, tag.eedc_kwh, tag.sc_kwh].filter((v): v is number => v !== null)
                const mean = prognosen.length > 1 ? prognosen.reduce((a, b) => a + b, 0) / prognosen.length : null
                const devRef = ref ?? mean
                return (
                  <tr key={tag.datum} className="border-b border-gray-100 dark:border-gray-800">
                    <td className="py-2 px-2 text-center">
                      <div className="flex items-center justify-center gap-1">
                        <WetterIcon symbol={tag.wetter_symbol} className="h-4 w-4" />
                        {tag.temp_max !== null && <span className="text-xs text-gray-500">{tag.temp_max}°</span>}
                      </div>
                    </td>
                    <td className="py-2 px-2 text-gray-900 dark:text-white">{formatDatum(tag.datum)}</td>
                    <td className="py-2 px-2 text-right font-mono">
                      {tag.om_kwh.toFixed(1)}
                      {devRef !== null && <DevBadge prognose={tag.om_kwh} ist={devRef} />}
                    </td>
                    <td className={`py-2 px-2 text-right font-mono ${hasEedc ? 'text-orange-500' : 'text-gray-400'}`}>
                      {hasEedc ? (
                        <>
                          {tag.eedc_kwh?.toFixed(1) ?? '—'}
                          {devRef !== null && tag.eedc_kwh !== null && <DevBadge prognose={tag.eedc_kwh} ist={devRef} />}
                        </>
                      ) : '—'}
                    </td>
                    {hasSolcast && (
                      <td className="py-2 px-2 text-right font-mono">
                        {tag.sc_kwh !== null ? (
                          <>
                            <span className="font-semibold">{tag.sc_kwh.toFixed(1)}</span>
                            {devRef !== null && <DevBadge prognose={tag.sc_kwh} ist={devRef} />}
                            <span className="text-gray-400 text-xs ml-1">({tag.sc_p10?.toFixed(0)}–{tag.sc_p90?.toFixed(0)})</span>
                          </>
                        ) : '—'}
                      </td>
                    )}
                    <td className="py-2 pl-2 pr-3 text-right font-mono font-semibold text-green-600 dark:text-green-400">
                      {tag.ist_kwh !== null ? tag.ist_kwh.toFixed(1) : <span className="text-gray-400 text-xs">⌀{mean?.toFixed(0)}</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        </DatendichtFallback>
      </Card>

      {/* ── Genauigkeits-Tracking ── */}
      {genauigkeit && genauigkeit.anzahl_tage > 0 && (
        <Card>
          <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Genauigkeits-Tracking <span className="text-sm font-normal text-gray-500 ml-2">(letzte {genauigkeit.anzahl_tage} Tage)</span>
            </h3>
            <div className="flex rounded-lg border border-gray-300 dark:border-gray-600 text-xs overflow-hidden">
              <button
                type="button"
                onClick={() => setGenauigkeitsModus('kompakt')}
                className={`px-3 py-1 transition-colors ${genauigkeitsModus === 'kompakt' ? 'bg-primary-600 text-white' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'}`}
              >
                Kompakt
              </button>
              <button
                type="button"
                onClick={() => setGenauigkeitsModus('diagnostisch')}
                className={`px-3 py-1 transition-colors ${genauigkeitsModus === 'diagnostisch' ? 'bg-primary-600 text-white' : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'}`}
              >
                Diagnostisch
              </button>
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
            {genauigkeitsModus === 'kompakt' ? (
              <>
                <MaeMbeCard label="OpenMeteo" mae={genauigkeit.openmeteo_mae_prozent} mbe={genauigkeit.openmeteo_mbe_prozent} color="text-yellow-500" />
                <MaeMbeCard
                  label="EEDC"
                  mae={genauigkeit.eedc_mae_prozent}
                  mbe={genauigkeit.eedc_mbe_prozent}
                  color="text-orange-500"
                  hint={lf == null ? 'Lernfaktor noch nicht verfügbar' : undefined}
                />
                <MaeMbeCard label="Solcast" mae={genauigkeit.solcast_mae_prozent} mbe={genauigkeit.solcast_mbe_prozent} color="text-blue-500" />
              </>
            ) : (
              <>
                <AsymmetrieCard label="OpenMeteo" asym={genauigkeit.openmeteo_asymmetrie} color="text-yellow-500" />
                <AsymmetrieCard label="EEDC" asym={genauigkeit.eedc_asymmetrie} color="text-orange-500" hint={lf == null ? 'Lernfaktor noch nicht verfügbar' : undefined} />
                <AsymmetrieCard label="Solcast" asym={genauigkeit.solcast_asymmetrie} color="text-blue-500" />
              </>
            )}
          </div>
          <DatendichtFallback>
          <div className="overflow-x-auto">
            <table className="w-full text-sm table-fixed">
              <colgroup>
                <col className="w-28" />
                <col />
                <col />
                <col />
                <col />
              </colgroup>
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700">
                  <th className="text-left py-2 px-3 font-medium text-gray-500">Datum</th>
                  <th className="text-right py-2 px-3 font-medium text-yellow-500">OpenMeteo</th>
                  <th className={`text-right py-2 px-3 font-medium ${lf != null ? 'text-orange-500' : 'text-gray-400'}`}>
                    <SimpleTooltip text={lf == null ? 'Lernfaktor noch nicht verfügbar — siehe Hinweis oben' : `EEDC = ${progBasisLabel} × Lernfaktor ${lf.toFixed(3)}`}>
                      <span>EEDC</span>
                    </SimpleTooltip>
                  </th>
                  <th className="text-right py-2 px-3 font-medium text-blue-500">Solcast</th>
                  <th className="text-right py-2 px-3 font-medium text-green-500">IST</th>
                </tr>
              </thead>
              <tbody>
                {genauigkeit.tage.slice(-7).reverse().map((tag) => (
                  <tr key={tag.datum} className="border-b border-gray-100 dark:border-gray-800">
                    <td className="py-2 px-3 text-gray-900 dark:text-white">{formatDatum(tag.datum)}</td>
                    <td className="py-2 px-3 text-right font-mono">{tag.openmeteo_kwh !== null ? <AbweichungCell prognose={tag.openmeteo_kwh} ist={tag.ist_kwh} /> : '—'}</td>
                    <td className="py-2 px-3 text-right font-mono">{tag.eedc_kwh !== null ? <AbweichungCell prognose={tag.eedc_kwh} ist={tag.ist_kwh} /> : <span className="text-gray-400">—</span>}</td>
                    <td className="py-2 px-3 text-right font-mono">{tag.solcast_kwh !== null ? <AbweichungCell prognose={tag.solcast_kwh} ist={tag.ist_kwh} /> : <span className="text-gray-400">—</span>}</td>
                    <td className="py-2 px-3 text-right font-mono font-semibold text-green-600 dark:text-green-400">{tag.ist_kwh !== null ? tag.ist_kwh.toFixed(1) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </DatendichtFallback>
        </Card>
      )}

      {/* ── Integrations-Vorschlag ── */}
      <Card className="bg-gray-50 dark:bg-gray-800/30 border-gray-200 dark:border-gray-700">
        <div className="flex gap-3">
          <Info className="h-5 w-5 text-blue-400 mt-0.5 shrink-0" />
          <div className="text-sm text-gray-600 dark:text-gray-300 space-y-4">
            <p className="font-semibold text-gray-800 dark:text-white">Integrations-Plan: Solcast-Daten in EEDC</p>
            <div className="space-y-3">
              <IntegrationItem icon={<Zap className="h-4 w-4 text-yellow-500" />} title="Live → Tagesverlauf + Wetter-Widget"
                text="Solcast als zusätzliche Linie im Tagesverlauf-Chart (30-Min-Auflösung, feinere Wolkenmuster). Solcast-Tagesprognose als KPI im Wetter-Widget. Solcast liefert direkte PV-Leistung (kW) — keine GTI-Umrechnung nötig." />
              <IntegrationItem icon={<Calendar className="h-4 w-4 text-blue-500" />} title="Aussichten → Kurzfristig (14-Tage)"
                text="Solcast-Balken neben OpenMeteo (Tag 1–7), p10/p90 als Fehlerbalken. Ab Tag 8: nur OpenMeteo (Solcast-Horizont = 7 Tage)." />
              <IntegrationItem icon={<BarChart3 className="h-4 w-4 text-green-500" />} title="Lernfaktor-Verbesserung"
                text="Solcast als Zweit-Referenz: Weichen beide Quellen gleich vom IST ab → Anlagen-Problem (Verschattung, Verschmutzung). Nur OpenMeteo weicht ab → Modell-Schwäche." />
              <IntegrationItem icon={<Sun className="h-4 w-4 text-purple-500" />} title="Finanzprognose + Speicher-Dimensionierung"
                text="Konfidenzband p10/p90 kalibriert die festen ±15% Unsicherheit bei PVGIS-Monatsprognosen. Für Speicher-Simulation: Min/Max-Szenarien (p10 = schlechter Tag, p90 = guter Tag)." />
              <IntegrationItem icon={<BarChart3 className="h-4 w-4 text-emerald-500" />} title="Blended Forecast (Ziel)"
                text="Nach ausreichend Vergleichsdaten: gewichteter Mittelwert — Solcast-dominant für Tag 1–2 (Satellit), OpenMeteo-dominant ab Tag 3+ (Wettermodell). Gewichte aus MAE-Tracking ableitbar." />
            </div>
            <p className="text-xs text-gray-400 border-t border-gray-200 dark:border-gray-700 pt-2">
              <span className="text-yellow-500">OpenMeteo</span> = Wettermodelle (ICON/ECMWF), GTI→kWh, 14 Tage, unbegrenzt.{' '}
              <span className="text-orange-500">EEDC</span> = {progBasisLabel} × Lernfaktor ({lf?.toFixed(3) ?? 'noch nicht verfügbar'}), MOS-kalibriert{data.eedc_lernfaktor_stufe ? ` (${data.eedc_lernfaktor_stufe})` : ''}.{' '}
              <span className="text-blue-500">Solcast</span> = Satellit + NWP, direkte PV-Leistung mit p10/p50/p90, 7 Tage.
            </p>
          </div>
        </div>
      </Card>
    </div>
  )
}


// ── Hilfskomponenten ──

function round(n: number, d: number) { const f = 10 ** d; return Math.round(n * f) / f }

function fmtKwh(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return `${v.toFixed(1)} kWh`
}

function fmtKwhBand(v: number | null, p10: number | null, p90: number | null): JSX.Element {
  if (v === null) return <span className="text-gray-400">—</span>
  return (
    <span>
      <span className="font-semibold">{v.toFixed(1)}</span>
      {p10 != null && p90 != null && (p10 > 0 || p90 > 0) && (
        <span className="text-gray-400 text-xs ml-1">({p10.toFixed(0)}–{p90.toFixed(0)})</span>
      )}
      <span className="text-gray-500 ml-1">kWh</span>
    </span>
  )
}

function fmtVmNm(th: { vormittag_kwh: number; nachmittag_kwh: number } | null): string {
  if (!th) return '—'
  return `${th.vormittag_kwh} / ${th.nachmittag_kwh}`
}

function IntegrationItem({ icon, title, text }: { icon: JSX.Element; title: string; text: string }) {
  return (
    <div className="flex gap-2">
      <div className="mt-0.5 shrink-0">{icon}</div>
      <div>
        <p className="font-medium">{title}</p>
        <p className="text-gray-500 dark:text-gray-400 text-xs">{text}</p>
      </div>
    </div>
  )
}

function MaeMbeCard({ label, mae, mbe, color, hint }: {
  label: string
  mae: number | null
  mbe: number | null
  color: string
  hint?: string
}) {
  const fmtMbe = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(0)}%`
  return (
    <div className="text-center p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
      <div className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{label}</div>
      <div className="flex items-baseline justify-center gap-3">
        <SimpleTooltip text="MAE = Mean Absolute Error: durchschnittliche Abweichung |Prognose − IST| in % — Streuung">
          <div>
            <span className="text-xs text-gray-500 mr-1">MAE</span>
            <span className={`text-lg font-bold ${color}`}>{mae !== null ? `${mae.toFixed(0)}%` : '—'}</span>
          </div>
        </SimpleTooltip>
        <SimpleTooltip text="MBE = Mean Bias Error: durchschnittliche vorzeichenbehaftete Abweichung — positiv = systematisch zu hoch, negativ = zu niedrig. |MBE| ≪ MAE → Streuung; |MBE| ≈ MAE → systematischer Bias (Lernfaktor wirkt).">
          <div>
            <span className="text-xs text-gray-500 mr-1">Bias</span>
            <span className={`text-lg font-bold ${mbe === null ? 'text-gray-400' : 'text-gray-700 dark:text-gray-200'}`}>
              {mbe !== null ? fmtMbe(mbe) : '—'}
            </span>
          </div>
        </SimpleTooltip>
      </div>
      {hint && <div className="text-[10px] text-gray-400 dark:text-gray-500 mt-1">{hint}</div>}
    </div>
  )
}

function AsymmetrieCard({ label, asym, color, hint }: {
  label: string
  asym: AsymmetrieEintrag | null
  color: string
  hint?: string
}) {
  const fmtPct = (v: number | null) => v === null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(0)}%`
  const overCount = asym?.over_count ?? 0
  const underCount = asym?.under_count ?? 0
  const tagWord = (n: number) => n === 1 ? 'Tag' : 'Tage'

  return (
    <div className="text-center p-3 rounded-lg bg-gray-50 dark:bg-gray-800/50">
      <div className={`text-xs font-medium mb-2 ${color}`}>{label}</div>
      <div className="grid grid-cols-2 gap-2">
        <SimpleTooltip text="Tage an denen die Prognose über dem IST lag — durchschnittliche relative Überschätzung">
          <div className="px-2 py-1.5 rounded bg-white dark:bg-gray-900/60 border border-gray-200 dark:border-gray-700">
            <div className="text-[10px] text-gray-500 dark:text-gray-400">darüber</div>
            <div className="text-sm font-bold text-amber-600 dark:text-amber-400">{fmtPct(asym?.over_avg_prozent ?? null)}</div>
            <div className="text-[10px] text-gray-400 dark:text-gray-500">{overCount} {tagWord(overCount)}</div>
          </div>
        </SimpleTooltip>
        <SimpleTooltip text="Tage an denen die Prognose unter dem IST lag — durchschnittliche relative Unterschätzung">
          <div className="px-2 py-1.5 rounded bg-white dark:bg-gray-900/60 border border-gray-200 dark:border-gray-700">
            <div className="text-[10px] text-gray-500 dark:text-gray-400">darunter</div>
            <div className="text-sm font-bold text-sky-600 dark:text-sky-400">{fmtPct(asym?.under_avg_prozent ?? null)}</div>
            <div className="text-[10px] text-gray-400 dark:text-gray-500">{underCount} {tagWord(underCount)}</div>
          </div>
        </SimpleTooltip>
      </div>
      {hint && <div className="text-[10px] text-gray-400 dark:text-gray-500 mt-1">{hint}</div>}
    </div>
  )
}

function DevBadge({ prognose, ist }: { prognose: number; ist: number }) {
  if (ist < 0.05 && prognose < 0.05) return null
  const diff = prognose - ist
  if (Math.abs(diff) < 0.03) return null
  const pct = ist > 0.05 ? Math.abs(diff / ist) * 100 : (prognose > 0.05 ? 100 : 0)
  const color = pct < 10 ? 'text-green-500' : pct < 30 ? 'text-yellow-500' : 'text-red-400'
  const arrow = diff > 0 ? '▲' : '▼'
  return <span className={`text-[10px] ml-1 ${color}`}>{arrow} {Math.abs(diff).toFixed(1)}</span>
}

function AbweichungCell({ prognose, ist }: { prognose: number; ist: number | null }) {
  if (ist === null || ist < 0.5) return <span>{prognose.toFixed(1)}</span>
  const pct = ((prognose - ist) / ist) * 100
  const color = Math.abs(pct) < 10 ? 'text-green-500' : Math.abs(pct) < 30 ? 'text-yellow-500' : 'text-red-500'
  return <span>{prognose.toFixed(1)}<span className={`text-xs ml-1 ${color}`}>{pct > 0 ? '+' : ''}{pct.toFixed(0)}%</span></span>
}

interface StundenTooltipPayload {
  dataKey?: string
  value?: number | null
  stroke?: string
  fill?: string
}

interface StundenTooltipProps {
  active?: boolean
  payload?: StundenTooltipPayload[]
  label?: string | number
  hasEedc?: boolean
}

function StundenTooltip({ active, payload, label, hasEedc }: StundenTooltipProps) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-gray-800 text-white p-2 rounded shadow-lg text-xs">
      <div className="font-medium mb-1">{label} Uhr</div>
      {payload.map((p: StundenTooltipPayload) => {
        const key = p.dataKey ?? ''
        if (['solcast_p10', 'solcast_p90'].includes(key)) return null
        if (key === 'ist' && p.value === null) return null
        if (key === 'eedc' && !hasEedc) return null
        const labels: Record<string, string> = { openmeteo: 'OpenMeteo (roh)', eedc: 'EEDC (kalibriert)', solcast: 'Solcast', ist: 'IST' }
        return (
          <div key={key} className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: p.stroke || p.fill }} />
            <span className="text-gray-400">{labels[key] || key}:</span>
            <span className="font-mono font-medium">{p.value?.toFixed(2)} kW</span>
          </div>
        )
      })}
    </div>
  )
}
