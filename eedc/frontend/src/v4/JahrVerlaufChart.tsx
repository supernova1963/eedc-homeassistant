/**
 * JahrVerlaufChart — „Verlauf"-Hauptblock der Cockpit/Jahr-Sicht.
 *
 * Granularitäts-agnostisches Pendant zu {@link TagesverlaufChart}: derselbe
 * gestapelte Bilanz-Balken-Chart, hier auf die MONATE des gewählten Jahres
 * angewandt (Monat→Tage, Tag→Stunden, Jahr→Monate). Toggles identisch:
 *   • Erzeugung  — Eigenverbrauch + Einspeisung = PV · Netzbezug separat
 *   • Verbrauch  — Direktverbrauch + Speicher-Entladung + Netzbezug = Gesamtverbrauch
 *   • Autarkie % — optionale Linie auf zweiter (%)-Achse
 *
 * Quelle: `AggregierteMonatsdaten[]` (Σ der IMD je Monat) — dieselbe SoT wie die
 * Bilanz-Vergleichsspalten, damit Chart und Zahlen nie auseinanderlaufen.
 */
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { ChartLegende, SegmentControl, eedcTooltipProps } from '../components/ui'
import { CHART_COLORS, MONAT_KURZ, xAchse, yAchse, achsenEinheit, achsenTick, ACHSEN_MARGIN_TOP, fmtZahl } from '../lib'
import { useLegendenToggle, useSchmaleAchse } from '../hooks'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'
import { vergleichBalken } from './VergleichBalken'
import { verfuegbarePresets, monatDrillInPfad } from './verlaufVergleich'

type BilanzView = 'erzeugung' | 'verbrauch' | 'vergleich'

interface ChartPunkt {
  monat: string
  /** Jahr + Monatsnummer — Drill-in-Ziel (B3, Balken-Klick → Cockpit/Monat). */
  jahr: number
  monatNr: number
  eigenverbrauch: number
  einspeisung: number
  netzbezug: number
  direktverbrauch: number
  speicherEntladung: number
  autarkie: number | null
  // R17/Vergleich-Modus (ungestackt) — Serien-Keys aus verlaufVergleich.
  pvAnlage: number
  bkw: number
  neg51: number
  speicherLadung: number
  netzladung: number
  eautoLadung: number
  eautoKm: number
}

const round1 = (v: number | null | undefined): number => (v == null ? 0 : Math.round(v * 10) / 10)

/** Pro Monat des Jahres die Bilanz-Werte (aufsteigend nach Monat). */
export function baueJahrChartDaten(monate: AggregierteMonatsdaten[]): ChartPunkt[] {
  return [...monate]
    .sort((a, b) => a.monat - b.monat)
    .map((m) => ({
      monat: MONAT_KURZ[m.monat],
      jahr: m.jahr,
      monatNr: m.monat,
      eigenverbrauch: round1(m.eigenverbrauch_kwh),
      einspeisung: round1(m.einspeisung_kwh),
      netzbezug: round1(m.netzbezug_kwh),
      direktverbrauch: round1(m.direktverbrauch_kwh),
      speicherEntladung: round1(m.speicher_entladung_kwh),
      autarkie: m.autarkie_prozent != null ? round1(m.autarkie_prozent) : null,
      pvAnlage: round1(m.pv_module_kwh),
      bkw: round1(m.bkw_kwh),
      neg51: round1(m.einspeisung_neg_preis_kwh),
      speicherLadung: round1(m.speicher_ladung_kwh),
      netzladung: round1(m.speicher_netzladung_kwh),
      eautoLadung: round1(m.eauto_ladung_kwh),
      eautoKm: round1(m.eauto_km),
    }))
}

export function JahrVerlaufChart({ monate }: { monate: AggregierteMonatsdaten[] }) {
  const schmal = useSchmaleAchse()
  const navigate = useNavigate()
  const [view, setView] = useState<BilanzView>('erzeugung')
  const [presetKey, setPresetKey] = useState('verbrauch')
  const [showAutarkie, setShowAutarkie] = useState(false)
  // Skalen-Lesbarkeit: Serien per Legenden-Klick aus-/einblenden (B7-Standard,
  // SoT-Hook). Reset bei Modus-/Preset-Wechsel — der Serien-Satz ändert sich.
  const legende = useLegendenToggle(`${view}:${presetKey}`)
  const daten = useMemo(() => baueJahrChartDaten(monate), [monate])
  const presets = verfuegbarePresets(true)
  const aktPreset = presets.find((p) => p.key === presetKey) ?? presets[0]

  if (monate.length === 0) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Monatsdaten im Jahr.</p>
  }

  return (
    <div className="space-y-3">
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
            : 'Ungestackt — je Kennzahl ein Balken, zum Vergleich der Monate'}
      </p>

      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={daten} margin={{ top: ACHSEN_MARGIN_TOP, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
            <XAxis dataKey="monat" {...xAchse(schmal)} /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
            <YAxis yAxisId="kwh" {...yAchse(schmal, 48)} tickFormatter={(v) => fmtZahl(v, 0)} label={achsenEinheit('kWh')} />
            {showAutarkie && view !== 'vergleich' && (
              <YAxis yAxisId="pct" orientation="right" domain={[0, 100]} {...yAchse(schmal, 40)} tickFormatter={achsenTick} label={achsenEinheit('%', 'rechts')} />
            )}
            <Tooltip {...eedcTooltipProps({ formatter: (value: number, name: string) =>
              name === 'Autarkie' ? `${fmtZahl(value, 1)} %`
                : name === 'Fahrleistung' ? `${fmtZahl(value, 0)} km`
                : `${fmtZahl(value, 1)} kWh` })} />
            <Legend wrapperStyle={{ fontSize: 12 }} content={
              // B7: Legenden-Klick blendet Serien aus/ein (Skalen-Lesbarkeit) — alle Modi.
              <ChartLegende onItemClick={legende.onItemClick} />
            } />

            {view === 'vergleich' ? (
              // B3: Balken-Klick → Cockpit/Monat des geklickten Monats (Ausreißer „reinklicken").
              // Als FUNKTION aufgerufen → Fragment wird direktes ComposedChart-Kind
              // (Recharts erkennt Bars nur direkt/in Fragmenten, nicht in Custom-Komponenten).
              vergleichBalken({
                preset: aktPreset,
                istJahr: true,
                schmal,
                onBarClick: (i) => navigate(monatDrillInPfad(daten[i].jahr, daten[i].monatNr)),
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
