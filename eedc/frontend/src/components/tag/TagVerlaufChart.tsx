/**
 * TagVerlaufChart — Butterfly-Stundenchart eines Tages (Quellen ▲ / Senken ▼).
 *
 * Aus der IST-„Tagesdetail"-Sicht (`pages/auswertung/EnergieprofilTab.tsx`)
 * extrahiert, damit Cockpit/Tag (v4) und die IST-Seite EINE Code-Wahrheit teilen
 * (Konvergenz-Leitprinzip, wie Aussicht ↔ EnergieprofilPrognose). Reine
 * Darstellung aus `StundenWert[]` + `SerieInfo[]` (extra Serien) — kein Daten-Laden.
 * Farben ausschließlich aus `lib` (kein Inline-Hex, Regel 0a).
 */
import { useMemo } from 'react'
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { ChartLegende, eedcTooltipProps } from '../ui'
import { EXTRA_SERIEN_FARBEN, KATEGORIE_FARBEN, CHART_LABELS, HILFSLINIE_DASH, AREA_FILL_OPACITY, xAchse, yAchse, achsenEinheit, achsenTick, ACHSEN_MARGIN_TOP, fmtZahl } from '../../lib'
import { useChartTheme } from '../../context/ThemeContext'
import { useLegendenToggle } from '../../hooks'
import type { StundenWert, SerieInfo } from '../../api/energie_profil'

function round2(v: number): number {
  return Math.round(v * 100) / 100
}

interface ChartSerie { dataKey: string; label: string; farbe: string; stackId: 'quellen' | 'senken'; hideLabel?: boolean }

export function TagVerlaufChart({ daten, extraSerien }: { daten: StundenWert[]; extraSerien: SerieInfo[] }) {
  const achsen = useChartTheme()
  // B7-Legenden-Toggle; Paar-Mapping: bidirektionale _pos/_neg-Serien (Batterie/Netz)
  // schalten gemeinsam über ihren Basis-Key (Legende zeigt nur den _pos-Eintrag).
  const { istVersteckt, toggleSerie } = useLegendenToggle()
  const basisKey = (k: string) => k.replace(/_(pos|neg)$/, '')
  const extraErzeuger    = useMemo(() => extraSerien.filter(s => s.seite === 'quelle'), [extraSerien])
  const extraVerbraucher = useMemo(() => extraSerien.filter(s => s.seite === 'senke'), [extraSerien])

  // Chart-Serien analog Live-TagesverlaufChart: bidirektionale in _pos/_neg aufgespalten.
  const chartSerien = useMemo<ChartSerie[]>(() => {
    const r: ChartSerie[] = []
    r.push({ dataKey: 'pv', label: 'PV', farbe: KATEGORIE_FARBEN.pv, stackId: 'quellen' })
    extraErzeuger.forEach((es, i) =>
      r.push({ dataKey: es.key, label: es.label, farbe: EXTRA_SERIEN_FARBEN[i % EXTRA_SERIEN_FARBEN.length], stackId: 'quellen' }))
    r.push({ dataKey: 'bat_pos', label: 'Batterie', farbe: KATEGORIE_FARBEN.batterie, stackId: 'quellen' })
    r.push({ dataKey: 'bat_neg', label: 'Batterie ↓', farbe: KATEGORIE_FARBEN.batterie, stackId: 'senken', hideLabel: true })
    r.push({ dataKey: 'netz_pos', label: 'Stromnetz', farbe: KATEGORIE_FARBEN.netz, stackId: 'quellen' })
    r.push({ dataKey: 'netz_neg', label: 'Stromnetz ↓', farbe: KATEGORIE_FARBEN.netz, stackId: 'senken', hideLabel: true })
    r.push({ dataKey: 'hausverbrauch', label: 'Hausverbrauch', farbe: KATEGORIE_FARBEN.haushalt, stackId: 'senken' })
    r.push({ dataKey: 'wp', label: 'Wärmepumpe', farbe: KATEGORIE_FARBEN.waermepumpe, stackId: 'senken' })
    r.push({ dataKey: 'wb', label: 'Wallbox', farbe: KATEGORIE_FARBEN.wallbox, stackId: 'senken' })
    extraVerbraucher.forEach((es, i) =>
      r.push({ dataKey: es.key, label: es.label, farbe: EXTRA_SERIEN_FARBEN[(extraErzeuger.length + i) % EXTRA_SERIEN_FARBEN.length], stackId: 'senken' }))
    return r
  }, [extraErzeuger, extraVerbraucher])

  const chartDaten = useMemo(() =>
    Array.from({ length: 24 }, (_, h) => {
      const s   = daten.find(d => d.stunde === h)
      const bat = s?.batterie_kw ?? 0
      const ntz = (s?.netzbezug_kw ?? 0) - (s?.einspeisung_kw ?? 0)
      const vbrSons = extraVerbraucher.reduce((a, es) => a + Math.abs(Math.min(0, s?.komponenten?.[es.key] ?? 0)), 0)
      const erzSons = extraErzeuger.reduce((a, es) => a + Math.max(0, s?.komponenten?.[es.key] ?? 0), 0)
      // `hausverbrauch` ist dieselbe Differenz wie in der Stundenwerte-Tabelle,
      // hier aber bewusst **ohne** die Unterdrückungs-Regel aus §3 des Konzepts
      // (`berechneHausverbrauch`): `Math.max(0, …)` klemmt den Ausdruck bei
      // fehlendem `verbrauch_kw` algebraisch auf 0 (alle Subtrahenden ≥ 0), der
      // Tooltip blendet Werte < 0,001 ohnehin aus — es entsteht also **keine**
      // falsche Zahl, nur ein Strich auf der Nulllinie. Ein `null` an dieser
      // Stelle ginge in eine **gestapelte** Fläche; dafür gibt es im Baum keine
      // Präzedenz und jsdom kann es nicht nachweisen. Wer die Serie anfasst,
      // zieht die Regel mit — s. `TagWerteTabelle.berechneHausverbrauch`.
      const punkt: Record<string, number | string> = {
        stunde:       `${h}:00`,
        pv:           s?.pv_kw ?? 0,
        bat_pos:      Math.max(0, bat),
        bat_neg:      Math.min(0, bat),
        netz_pos:     Math.max(0, ntz),
        netz_neg:     Math.min(0, ntz),
        hausverbrauch: -Math.max(0, (s?.verbrauch_kw ?? 0) - (s?.waermepumpe_kw ?? 0) - (s?.wallbox_kw ?? 0) - vbrSons),
        wp:           -(s?.waermepumpe_kw ?? 0),
        wb:           -(s?.wallbox_kw ?? 0),
        gesamterzeugung: round2((s?.pv_kw ?? 0) + Math.max(0, bat) + erzSons),
      }
      for (const es of extraErzeuger)    punkt[es.key] = Math.max(0, s?.komponenten?.[es.key] ?? 0)
      for (const es of extraVerbraucher) punkt[es.key] = Math.min(0, s?.komponenten?.[es.key] ?? 0)
      return punkt
    }), [daten, extraErzeuger, extraVerbraucher])

  return (
    // D18-3 (detlan #210): KEINE eigene <Card> mehr um den Chart — die
    // Gliederungsebene (BlockShell-Body px-3) trägt den Seitenrand, die
    // IST-Seite hüllt am Aufrufer. YAxis-Breite aus chartAchse (44, wie das
    // Vorbild KomponentenVerlaufChart) statt Recharts-Default 60.
    <div>
      <div className="text-[10px] text-gray-400 dark:text-gray-500 mb-1 flex justify-between">
        <span>▲ Quellen (Erzeugung, Bezug)</span>
        <span>Stundenmittelwerte aus Energieprofil · gestrichelt = Verfügbare Energie</span>
        <span>▼ Senken (Verbrauch, Einspeisung)</span>
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={chartDaten} margin={{ top: ACHSEN_MARGIN_TOP, right: 10, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
          <XAxis dataKey="stunde" {...xAchse()} interval={2} /* achsen-allow: Zeit-/Kategorie-Achse (Stunde) */ />
          <YAxis {...yAchse(false, 44)} tickFormatter={achsenTick} label={achsenEinheit('kW')} />
          <ReferenceLine y={0} stroke={achsen.referenz} strokeWidth={1.5} />
          <Tooltip {...eedcTooltipProps({
            unit: ' kW', decimals: 2,
            nameFormatter: (name) => chartSerien.find(cs => cs.dataKey === name)?.label ?? CHART_LABELS[name] ?? name,
            formatter: (v) => Math.abs(v) < 0.001 ? null : `${v > 0 ? '▲' : '▼'} ${fmtZahl(Math.abs(v), 2)} kW`,
          })} />
          <Legend content={<ChartLegende
            formatter={(value) => chartSerien.find(cs => cs.dataKey === value)?.label ?? value}
            onItemClick={(e) => toggleSerie(basisKey(String(e.dataKey ?? e.value)))}
          />} />

          {chartSerien.map(cs => (
            <Area
              key={cs.dataKey}
              type="monotone"
              dataKey={cs.dataKey}
              name={cs.dataKey}
              fill={cs.farbe}
              stroke={cs.farbe}
              fillOpacity={AREA_FILL_OPACITY}
              strokeWidth={1.5}
              stackId={cs.stackId}
              isAnimationActive={false}
              legendType={cs.hideLabel ? 'none' : undefined}
              hide={istVersteckt(basisKey(cs.dataKey))}
            />
          ))}

          {/* Summen-/Hilfslinie (keine Prognose) → HILFSLINIE_DASH, nicht PROGNOSE_DASH (Regel C).
              D17-1: neutrale Hilfslinien-Farbe (nicht COLORS.solar = PV-Rolle) — sonst wirkte
              „Gesamterzeugung" im Tooltip wie eine Farb-/Wert-Dublette der PV-Zeile. Label
              „Gesamterzeugung" (groß) kommt aus CHART_LABELS (nameFormatter-Fallback oben). */}
          <Line dataKey="gesamterzeugung" name="gesamterzeugung"
            stroke={achsen.referenz} strokeWidth={2} strokeDasharray={HILFSLINIE_DASH}
            dot={false} connectNulls legendType="none" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
