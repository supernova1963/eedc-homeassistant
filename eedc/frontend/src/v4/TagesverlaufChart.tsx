/**
 * TagesverlaufChart — „Verlauf"-Hauptblock der Cockpit/Monat-Sicht (IA v4 E3, B4).
 *
 * Gestapelter Tages-Balken-Chart im bewährten Stil der IST-Auswertung
 * („Energie-Bilanz pro Monat", `pages/auswertung/EnergieTab.tsx`), hier aber auf
 * die TAGE des gewählten Monats angewandt (granularitäts-agnostisches Prinzip:
 * Monat→Tage, später Tag→Stunden / Jahr→Monate). Toggles:
 *   • Erzeugung  — Eigenverbrauch + Einspeisung gestapelt (= PV) · Netzbezug separat
 *   • Verbrauch  — Direktverbrauch + Speicher-Entladung + Netzbezug gestapelt
 *                  (= Gesamtverbrauch) · Einspeisung separat  ← Direktverbrauch-Detail
 *   • Autarkie % — optionale Linie auf zweiter (%)-Achse
 *
 * Datenquelle: `TagWerte[]` (Tages-Werte-Endpoint) — dieselbe SoT wie die
 * Auswertungen/Tabelle, damit Chart und Zahlen nie auseinanderlaufen.
 */
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { ChartLegende, SegmentControl, eedcTooltipProps } from '../components/ui'
import { CHART_COLORS, xAchse, yAchse, achsenEinheit, achsenTick, ACHSEN_MARGIN_TOP, fmtZahl } from '../lib'
import { useLegendenToggle, useSchmaleAchse } from '../hooks'
import type { TagWerte } from '../api/energie_profil'
import { vergleichBalken } from './VergleichBalken'
import { verfuegbarePresets, tagDrillInPfad } from './verlaufVergleich'

type BilanzView = 'erzeugung' | 'verbrauch' | 'vergleich'

interface ChartPunkt {
  tag: number
  /** ISO-Datum des Tages — Drill-in-Ziel (B3, Balken-Klick → Cockpit/Tag). */
  datum: string
  /** `null` = die Achse war an dem Tag nicht erfasst (Lücke im Balken statt
   *  einer 0). Galt bis 15.08.2026 nur für die PV-abhängigen Größen; seit
   *  T89667 #162 sagen Einspeisung, Netzbezug und Direktverbrauch es ebenso. */
  eigenverbrauch: number | null
  einspeisung: number | null
  netzbezug: number | null
  direktverbrauch: number | null
  speicherEntladung: number
  autarkie: number | null
  // R17/Vergleich-Modus (ungestackt) — Serien-Keys aus verlaufVergleich.
  pvAnlage: number
  bkw: number
  neg51: number
  speicherLadung: number
}

/** Pro Tag des Monats die Bilanz-Werte (aufsteigend nach Datum). */
export function baueChartDaten(tage: TagWerte[]): ChartPunkt[] {
  return [...tage]
    .sort((a, b) => a.datum.localeCompare(b.datum))
    .map((t) => ({
      tag: Number(t.datum.slice(8, 10)),
      datum: t.datum,
      // null bleibt null: der Chart zeigt eine Lücke statt einer 0-Fläche,
      // wenn die Achse an dem Tag nicht erfasst war.
      eigenverbrauch: t.eigenverbrauch != null ? round1(t.eigenverbrauch) : null,
      einspeisung: t.einspeisung != null ? round1(t.einspeisung) : null,
      netzbezug: t.netzbezug != null ? round1(t.netzbezug) : null,
      direktverbrauch: t.direktverbrauch != null ? round1(t.direktverbrauch) : null,
      speicherEntladung: round1(t.speicher_entladung ?? 0),
      autarkie: t.autarkie != null ? round1(t.autarkie) : null,
      pvAnlage: round1(t.pv_anlage),
      bkw: round1(t.bkw),
      neg51: round1(t.einspeisung_neg_preis_kwh ?? 0),
      speicherLadung: round1(t.speicher_ladung ?? 0),
    }))
}

export function TagesverlaufChart({ tage }: { tage: TagWerte[] }) {
  const schmal = useSchmaleAchse()
  const navigate = useNavigate()
  const [view, setView] = useState<BilanzView>('erzeugung')
  const [presetKey, setPresetKey] = useState('verbrauch')
  const [showAutarkie, setShowAutarkie] = useState(false)
  // Skalen-Lesbarkeit: einzelne Serien per Legenden-Klick aus-/einblenden (B7-Standard,
  // SoT-Hook). Reset bei Modus-/Preset-Wechsel — der Serien-Satz ändert sich.
  const legende = useLegendenToggle(`${view}:${presetKey}`)
  const daten = useMemo(() => baueChartDaten(tage), [tage])
  const presets = verfuegbarePresets(false)
  const aktPreset = presets.find((p) => p.key === presetKey) ?? presets[0]

  if (tage.length === 0) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Tagesdaten im Monat.</p>
  }

  return (
    <div className="space-y-3">
      {/* Toggles: Erzeugung/Verbrauch + Autarkie % (wie IST-Auswertung) */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <SegmentControl
          ariaLabel="Bilanz-Ansicht"
          optionen={[
            { key: 'erzeugung', label: 'Erzeugung' },
            { key: 'verbrauch', label: 'Verbrauch' },
            { key: 'vergleich', label: 'Vergleich' },
          ]}
          value={view} onChange={setView}
        />
        {view === 'vergleich' ? (
          <SegmentControl
            ariaLabel="Vergleich-Kennzahl"
            optionen={presets.map((p) => ({ key: p.key, label: p.label }))}
            value={aktPreset.key} onChange={setPresetKey}
          />
        ) : (
          <button
            type="button"
            onClick={() => setShowAutarkie((s) => !s)}
            className={`min-h-[36px] px-3 text-sm font-medium rounded-lg border transition-colors ${
              showAutarkie
                ? 'border-blue-300 bg-blue-50 text-blue-700 dark:border-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
                : 'border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800'
            }`}
          >
            Autarkie %
          </button>
        )}
      </div>

      <p className="text-xs text-gray-400 dark:text-gray-500">
        {view === 'erzeugung'
          ? 'Gestapelt: Eigenverbrauch + Einspeisung = PV-Erzeugung'
          : view === 'verbrauch'
            ? 'Gestapelt: Direktverbrauch + Speicher-Entladung + Netzbezug = Gesamtverbrauch'
            : 'Ungestackt — je Kennzahl ein Balken, zum Vergleich der Tage'}
      </p>

      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={daten} margin={{ top: ACHSEN_MARGIN_TOP, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
            <XAxis dataKey="tag" {...xAchse(schmal)} /* achsen-allow: Zeit-/Kategorie-Achse (Tag) */ />
            <YAxis yAxisId="kwh" {...yAchse(schmal, 48)} tickFormatter={(v) => fmtZahl(v, 0)} label={achsenEinheit('kWh')} />
            {showAutarkie && view !== 'vergleich' && (
              <YAxis yAxisId="pct" orientation="right" domain={[0, 100]} {...yAchse(schmal, 40)} tickFormatter={achsenTick} label={achsenEinheit('%', 'rechts')} />
            )}
            <Tooltip {...eedcTooltipProps({ formatter: (value: number, name: string) =>
              name === 'Autarkie' ? `${fmtZahl(value, 1)} %` : `${fmtZahl(value, 1)} kWh` })} />
            <Legend wrapperStyle={{ fontSize: 12 }} content={
              // B7: Legenden-Klick blendet Serien aus/ein (Skalen-Lesbarkeit) — alle Modi.
              <ChartLegende onItemClick={legende.onItemClick} />
            } />

            {view === 'vergleich' ? (
              // B3: Balken-Klick → Cockpit/Tag des geklickten Tages (Ausreißer „reinklicken").
              // Als FUNKTION aufgerufen → Fragment wird direktes ComposedChart-Kind
              // (Recharts erkennt Bars nur direkt/in Fragmenten, nicht in Custom-Komponenten).
              vergleichBalken({
                preset: aktPreset,
                istJahr: false,
                schmal,
                onBarClick: (i) => navigate(tagDrillInPfad(daten[i].datum)),
                hidden: legende.versteckt,
              })
            ) : view === 'erzeugung' ? (
              <>
                <Bar yAxisId="kwh" dataKey="eigenverbrauch" name="Eigenverbrauch" stackId="pv" fill={CHART_COLORS.eigenverbrauch} hide={legende.istVersteckt('eigenverbrauch')} />
                <Bar yAxisId="kwh" dataKey="einspeisung" name="Einspeisung" stackId="pv" fill={CHART_COLORS.einspeisung} hide={legende.istVersteckt('einspeisung')} />
                <Bar yAxisId="kwh" dataKey="netzbezug" name="Netzbezug" fill={CHART_COLORS.netzbezug} hide={legende.istVersteckt('netzbezug')} />
              </>
            ) : (
              <>
                <Bar yAxisId="kwh" dataKey="direktverbrauch" name="Direktverbrauch" stackId="vb" fill={CHART_COLORS.direktverbrauch} hide={legende.istVersteckt('direktverbrauch')} />
                <Bar yAxisId="kwh" dataKey="speicherEntladung" name="Speicher-Entladung" stackId="vb" fill={CHART_COLORS.speicherEntladung} hide={legende.istVersteckt('speicherEntladung')} />
                <Bar yAxisId="kwh" dataKey="netzbezug" name="Netzbezug" stackId="vb" fill={CHART_COLORS.netzbezug} hide={legende.istVersteckt('netzbezug')} />
                <Bar yAxisId="kwh" dataKey="einspeisung" name="Einspeisung" fill={CHART_COLORS.einspeisung} hide={legende.istVersteckt('einspeisung')} />
              </>
            )}

            {showAutarkie && view !== 'vergleich' && (
              <Line yAxisId="pct" type="monotone" dataKey="autarkie" name="Autarkie" stroke={CHART_COLORS.autarkie} strokeWidth={2} dot={false} connectNulls hide={legende.istVersteckt('autarkie')} />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function round1(v: number): number {
  return Math.round(v * 10) / 10
}
