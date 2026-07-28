/**
 * Energieprofil Prognose — Etappe 3b Phase A
 *
 * Kombinierte Verbrauchs- + PV-Prognose für einen Tag mit Batterie-Simulation.
 * Zeigt: Stunden-Chart (PV vs. Verbrauch vs. Netto), SoC-Overlay, KPI-Cards.
 */
import { useState, useEffect, useMemo } from 'react'
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { Calendar, Battery, Zap, Sun, ArrowDown, ArrowUp, Info } from 'lucide-react'
import { Card, Alert, KPICard, ChartLegende, Table, TableHead, TableBody, TableFoot } from '../../components/ui'
import { ZELLE, KOPF_ZELLE } from '../../components/ui/tabelleMasse'
import { DatumPicker } from '../../components/ui/DatumPicker'
import { COLORS, CHART_COLORS, achsenEinheit, achsenTick, ACHSEN_MARGIN_TOP, fmtZahl, unvollstaendigHerkunft } from '../../lib'
import { HerkunftZeile } from '../../components/blocks'
import { useChartTheme } from '../../context/ThemeContext'
import { useLegendenToggle } from '../../hooks'
import { energieProfilApi, type TagesPrognose } from '../../api/energie_profil'

interface Props {
  anlageId: number
}

export function morgenISO(): string {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  return d.toISOString().slice(0, 10)
}

export function heuteISO(): string {
  return new Date().toISOString().slice(0, 10)
}

/** Max-Prognose-Datum = heute + 14 Tage (Picker-Obergrenze). */
export function maxPrognoseDatum(): string {
  const d = new Date()
  d.setDate(d.getDate() + 14)
  return d.toISOString().slice(0, 10)
}

function fmt1(v: number | null | undefined): string {
  if (v == null) return '—'
  return fmtZahl(v, 1)
}

function fmt0(v: number | null | undefined): string {
  if (v == null) return '—'
  return fmtZahl(v, 0)
}

const VERBRAUCH_BASIS_LABELS: Record<string, string> = {
  gleicher_wochentag: 'Gleicher Wochentag',
  tagestyp: 'Werktag/Wochenende',
  alle: 'Alle Tage',
}

const PV_QUELLE_LABELS: Record<string, string> = {
  openmeteo: 'Open-Meteo (kalibriert)',
  solcast: 'Solcast',
}

export function EnergieprofilPrognose({ anlageId }: Props) {
  const [datum, setDatum] = useState(morgenISO())
  const [daten, setDaten] = useState<TagesPrognose | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!anlageId || !datum) return
    setLoading(true)
    setError(null)
    energieProfilApi.getTagesprognose(anlageId, datum)
      .then(setDaten)
      .catch(err => {
        setDaten(null)
        const detail = err?.response?.data?.detail || err?.message || 'Fehler beim Laden'
        setError(detail)
      })
      .finally(() => setLoading(false))
  }, [anlageId, datum])

  const maxDatum = maxPrognoseDatum()

  return (
    <div className="space-y-4">
      {/* Datum-Picker */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Prognose für:</span>
        <DatumPicker
          modus="tag"
          value={datum}
          min={heuteISO()}
          max={maxDatum}
          onChange={setDatum}
          ariaLabel="Prognose-Datum"
        />
        <button
          type="button"
          onClick={() => setDatum(morgenISO())}
          className={`px-2 py-1 text-xs rounded font-medium transition-colors ${
            datum === morgenISO()
              ? 'bg-primary-100 text-primary-700 dark:bg-primary-900 dark:text-primary-300'
              : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
          }`}
        >
          Morgen
        </button>
        {loading && <span className="text-xs text-gray-400 dark:text-gray-500">Lade...</span>}
      </div>

      {/* Error */}
      {error && (
        <Alert type="warning">{error}</Alert>
      )}

      {/* Chart-Karte (KPIs + Verlauf + Meta) + Stundentabelle — als eigenständige
          Teile exportiert, damit Cockpit/Aussicht sie in getrennte Blöcke legen
          kann (Gernot 2026-06-23). IST-Seite zeigt beide untereinander wie bisher. */}
      {daten && (
        <>
          <PrognoseChartKarte daten={daten} />
          <PrognoseTabelle daten={daten} />
        </>
      )}

      {/* Leerzustand */}
      {!daten && !loading && !error && (
        <Card className="text-center py-10 text-gray-400 dark:text-gray-500 text-sm">
          <Calendar className="h-8 w-8 mx-auto mb-2 opacity-50" />
          Wähle ein Datum für die Tagesprognose.
        </Card>
      )}
    </div>
  )
}


// ── Chart-Karte (KPIs + Verlauf + Meta) ──────────────────────────────────────

export function PrognoseChartKarte({ daten }: { daten: TagesPrognose }) {
  const achsen = useChartTheme()
  const hatSpeicher = daten.speicher_kapazitaet_kwh != null
  // A28: ohne Verbrauchshistorie liefert das Backend nur die PV-Hälfte. `null`
  // statt 0 durchreichen — Recharts zeichnet dann KEINE Fläche; eine 0-Linie
  // würde „Verbrauch = 0" behaupten (P4).
  const hatVerbrauch = daten.verbrauch_summe_kwh != null
  const chartDaten = useMemo(() => daten.stunden.map(s => ({
    stunde: `${s.stunde}:00`,
    pv: s.pv_kw,
    verbrauch: s.verbrauch_kw != null ? -s.verbrauch_kw : null,  // negativ für Senken-Darstellung
    netto: s.netto_kw,
    netzbezug: s.netzbezug_kw != null && s.netzbezug_kw > 0 ? -s.netzbezug_kw : null,
    einspeisung: s.einspeisung_kw != null && s.einspeisung_kw > 0 ? s.einspeisung_kw : null,
    soc: s.soc_prozent,
  })), [daten])
  // R5-5c (Rainer): Serien per Legende an/aus — insb. die SoC-Linie, die manche
  // im Prognose-Chart nicht brauchen (B7-Standard, SoT-Hook). Nicht entfernen,
  // nur abschaltbar.
  const { istVersteckt, onItemClick } = useLegendenToggle()
  // P4: sagt die Antwort selbst, dass ihr PV-Profil unvollständig ist, steht das
  // DORT, wo die Zahl steht — über der PV-Kachel und der Summenzeile, nicht im Log.
  const herkunft = unvollstaendigHerkunft(daten.hinweise, hatVerbrauch ? 'PV-Prognose' : 'Prognose')
  return (
    <div className="space-y-4">
      <HerkunftZeile herkunft={herkunft} />
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
        <KPICard size="sm" icon={Sun} title="PV-Prognose" value={`${fmt1(daten.pv_summe_kwh)} kWh`} color="yellow" />
        <KPICard size="sm" icon={Zap} title="Verbrauch" value={`${fmt1(daten.verbrauch_summe_kwh)} kWh`} color="gray" />
        <KPICard size="sm" icon={ArrowDown} title="Netzbezug" value={`${fmt1(daten.netzbezug_summe_kwh)} kWh`} color="red" />
        <KPICard size="sm" icon={ArrowUp} title="Einspeisung" value={`${fmt1(daten.einspeisung_summe_kwh)} kWh`} color="cyan" />
        <KPICard size="sm" icon={Sun} title="Eigenverbrauch" value={`${fmt1(daten.eigenverbrauch_kwh)} kWh`} color="green" />
        <KPICard size="sm" icon={Zap} title="Autarkie" value={`${fmt0(daten.autarkie_prozent)} %`} color="green" />
        {hatSpeicher && (
          // Ohne Verbrauchsprognose gibt es keine Speicher-Simulation — „nicht
          // erreicht" wäre dann eine Aussage über einen Lauf, der nie stattfand.
          <KPICard size="sm" icon={Battery} title="Speicher voll" value={hatVerbrauch ? (daten.speicher_voll_um ?? 'nicht erreicht') : '—'} color="blue" />
        )}
      </div>

      <Card>
        <div className="text-[10px] text-gray-400 dark:text-gray-500 mb-1 flex justify-between">
          <span>PV-Prognose: {PV_QUELLE_LABELS[daten.pv_quelle] ?? daten.pv_quelle}</span>
          <span>
            {daten.verbrauch_basis != null
              ? `Verbrauch: ${VERBRAUCH_BASIS_LABELS[daten.verbrauch_basis] ?? daten.verbrauch_basis} (${daten.daten_tage} Tage)`
              : 'Verbrauch: noch keine Historie'}
          </span>
        </div>
        <ResponsiveContainer width="100%" height={360}>
          {/* D11-16 (detLAN „krassestes Beispiel"): right war 50 → großer Leerraum rechts
              (Recharts reserviert die SoC-Achsenbreite ohnehin separat). Auf 10 getrimmt. */}
          <ComposedChart data={chartDaten} margin={{ top: ACHSEN_MARGIN_TOP, right: hatSpeicher ? 10 : 8, left: -10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200 dark:stroke-gray-700" />
            {/* D11-16/Stunden: Labels überlappten mobil („0:003:00…") — −45° (konsistent
                mit der app-weiten 45°-Regel; eigener XAxis, da kein xAchse-Spread). */}
            <XAxis dataKey="stunde" tick={{ fontSize: 10 }} interval={2} angle={-45} textAnchor="end" height={40} /* achsen-allow: Zeit-/Kategorie-Achse */ />
            <YAxis yAxisId="kw" tick={{ fontSize: 10 }} tickFormatter={achsenTick} label={achsenEinheit('kW')} />
            {hatSpeicher && (
              <YAxis yAxisId="soc" orientation="right" domain={[0, 100]} tick={{ fontSize: 10 }} tickFormatter={achsenTick} label={achsenEinheit('%', 'rechts')} />
            )}
            <ReferenceLine yAxisId="kw" y={0} stroke={achsen.referenz} strokeWidth={1.5} />
            <Tooltip content={<PrognoseTooltip hatSpeicher={hatSpeicher} />} />
            <Legend wrapperStyle={{ fontSize: 11 }} content={<ChartLegende onItemClick={onItemClick} />} />
            <Area yAxisId="kw" type="monotone" dataKey="pv" name="PV-Prognose" fill={COLORS.solar} stroke={COLORS.solar} fillOpacity={0.3} strokeWidth={2} isAnimationActive={false} hide={istVersteckt('pv')} />
            <Area yAxisId="kw" type="monotone" dataKey="einspeisung" name="Einspeisung" fill={CHART_COLORS.einspeisung} stroke={CHART_COLORS.einspeisung} fillOpacity={0.2} strokeWidth={1} strokeDasharray="4 2" isAnimationActive={false} hide={istVersteckt('einspeisung')} />
            <Area yAxisId="kw" type="monotone" dataKey="verbrauch" name="Verbrauch" fill={COLORS.consumption} stroke={COLORS.consumption} fillOpacity={0.25} strokeWidth={2} isAnimationActive={false} hide={istVersteckt('verbrauch')} />
            <Area yAxisId="kw" type="monotone" dataKey="netzbezug" name="Netzbezug" fill={CHART_COLORS.netzbezug} stroke={CHART_COLORS.netzbezug} fillOpacity={0.2} strokeWidth={1} strokeDasharray="4 2" isAnimationActive={false} hide={istVersteckt('netzbezug')} />
            {hatSpeicher && (
              <Line yAxisId="soc" type="monotone" dataKey="soc" name="SoC" stroke={COLORS.battery} strokeWidth={2} dot={false} connectNulls hide={istVersteckt('soc')} />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </Card>

      <div className="flex items-start gap-2 text-xs text-gray-400 dark:text-gray-500">
        <Info className="h-3.5 w-3.5 mt-0.5 shrink-0" />
        <span>
          {daten.verbrauch_basis != null
            ? `Verbrauchsprognose basiert auf dem Ø-Stundenprofil der letzten ${daten.daten_tage} Tage (${VERBRAUCH_BASIS_LABELS[daten.verbrauch_basis] ?? daten.verbrauch_basis}).`
            : 'Für die Verbrauchsprognose fehlt noch die Historie — sie startet, sobald 3 vollständige Tage aufgezeichnet sind.'}
          {' '}PV-Prognose: {PV_QUELLE_LABELS[daten.pv_quelle] ?? daten.pv_quelle}.
          {/* A31-2: die Simulation läuft auf der nutzbaren Kapazität. Das muss
              hier stehen — sonst liest sich die Zahl als Tippfehler, wenn im
              Komponenten-Hub die (größere) Nennkapazität steht. */}
          {hatSpeicher && hatVerbrauch && ` Batterie-Simulation: ${fmt1(daten.speicher_kapazitaet_kwh)} kWh nutzbar, vereinfachtes Modell ohne Wirkungsgradverluste.`}
        </span>
      </div>
    </div>
  )
}


// ── Tooltip ──────────────────────────────────────────────────────────────────

function PrognoseTooltip({ active, payload, label }: {
  active?: boolean; payload?: Array<{ name: string; value: number; color: string }>; label?: string; hatSpeicher?: boolean
}) {
  if (!active || !payload) return null

  return (
    <div className="bg-gray-900 dark:bg-gray-950 border border-gray-700 rounded-lg shadow-lg px-3 py-2 text-xs">
      <p className="font-medium text-white mb-1">{label}</p>
      {payload.filter(p => p.value != null).map((p, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-sm" style={{ backgroundColor: p.color }} />
          <span className="text-gray-300">{p.name}:</span>
          <span className="font-medium text-white">
            {p.name === 'SoC' ? `${fmtZahl(p.value, 1)} %` : `${fmtZahl(Math.abs(p.value), 2)} kW`}
          </span>
        </div>
      ))}
    </div>
  )
}


// ── Stundentabelle ───────────────────────────────────────────────────────────

export function PrognoseTabelle({ daten, ohneCaption, istStunden, aktuelleStunde }: {
  daten: TagesPrognose
  ohneCaption?: boolean
  /**
   * Gemessene PV-Stundenwerte des HEUTIGEN Tages (R22-6, PN 89768 Rainer):
   * „Mit den IST-Einträgen meinte ich die bisherigen Stunden. Dann müsste man
   * nicht in die Auswertungen springen." Nur setzen, wenn das gewählte Datum
   * heute ist — für morgen gibt es kein IST. Undefined ⇒ Spalte entfällt,
   * die Tabelle bleibt exakt wie vorher.
   */
  istStunden?: { stunde: number; kw: number | null }[]
  /** Trennt vergangene von künftigen Stunden (dezente Hinterlegung). */
  aktuelleStunde?: number | null
}) {
  const hatSpeicher = daten.speicher_kapazitaet_kwh != null
  const istMap = new Map((istStunden ?? []).map(e => [e.stunde, e.kw]))
  const zeigtIst = istStunden != null
  const istSumme = (istStunden ?? []).reduce((s, e) => s + (e.kw ?? 0), 0)
  // P4: die Summenzeile unten IST die Zahl, um die es geht — die Kennzeichnung
  // muss auch hier stehen, nicht nur am Chart daneben (die Tabelle wird im
  // Fokus-Overlay allein gezeigt).
  const hatVerbrauch = daten.verbrauch_summe_kwh != null
  const herkunft = unvollstaendigHerkunft(daten.hinweise, hatVerbrauch ? 'PV-Prognose' : 'Prognose')

  return (
    <Card padding="none" className="overflow-hidden">
      {herkunft && (
        <div className={`${ZELLE} border-b border-gray-200 dark:border-gray-700`}>
          <HerkunftZeile herkunft={herkunft} />
        </div>
      )}
      {/* Caption unterdrückbar (`ohneCaption`), wenn ein Block-Header denselben Text
          schon als Summary zeigt (Cockpit/Aussicht „Stundenwerte") — sonst doppelt.
          Standalone (Energieprofil-Seite) bleibt sie die einzige Beschriftung. */}
      {!ohneCaption && (
        <div className={`${ZELLE} border-b border-gray-200 dark:border-gray-700`}>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            Stundenprognose in kW · Summenzeile = kWh/Tag
          </span>
        </div>
      )}
      {/* D17-2 (G16-1): alle 24 Stunden am Stück, kein innerer Vertikal-Scroll
          (max-h entfernt) — wie die Cockpit/Tag-Stundentabelle. Horizontaler Überlauf
          zeigt den ScrollSchatten-Fade; thead sticky bleibt (harmlos ohne Eigen-Scroll),
          tfoot NICHT sticky (schwebte sonst am Viewport-Boden). */}
      <Table zeilen={24} mitFuss flaeche="karte">
          <TableHead>
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th className={`${KOPF_ZELLE} text-left text-gray-500 dark:text-gray-400`}>Std</th>
              <th className={`${KOPF_ZELLE} text-right text-yellow-600 dark:text-yellow-400`}>PV</th>
              {zeigtIst && (
                <th className={`${KOPF_ZELLE} text-right text-gray-600 dark:text-gray-300`}>PV IST</th>
              )}
              <th className={`${KOPF_ZELLE} text-right text-gray-600 dark:text-gray-300`}>Verbr.</th>
              <th className={`${KOPF_ZELLE} text-right text-green-600 dark:text-green-400`}>Netto</th>
              <th className={`${KOPF_ZELLE} text-right text-red-600 dark:text-red-400`}>Bezug</th>
              <th className={`${KOPF_ZELLE} text-right text-cyan-600 dark:text-cyan-400`}>Einsp.</th>
              {hatSpeicher && (
                <th className={`${KOPF_ZELLE} text-right text-blue-600 dark:text-blue-400`}>SoC %</th>
              )}
            </tr>
          </TableHead>
          <TableBody>
            {daten.stunden.map(s => (
              <tr
                key={s.stunde}
                className={`border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/40${
                  zeigtIst && aktuelleStunde != null && s.stunde < aktuelleStunde
                    ? ' bg-gray-50/60 dark:bg-gray-800/30'
                    : ''
                }`}
              >
                <td className={`${ZELLE} font-medium text-gray-600 dark:text-gray-300 tabular-nums`}>{s.stunde}:00</td>
                <td className={`${ZELLE} text-right tabular-nums text-yellow-700 dark:text-yellow-300`}>{fmtZahl(s.pv_kw, 2)}</td>
                {zeigtIst && (
                  <td className={`${ZELLE} text-right tabular-nums font-medium text-gray-700 dark:text-gray-200`}>
                    {istMap.get(s.stunde) != null ? fmtZahl(istMap.get(s.stunde), 2) : <Dash />}
                  </td>
                )}
                {/* A28: ohne Verbrauchsprognose sind Verbrauch/Netto/Bezug/
                    Einspeisung `null` — „—" statt einer 0, die wie ein Messwert
                    aussähe (P4). */}
                <td className={`${ZELLE} text-right tabular-nums text-gray-700 dark:text-gray-300`}>
                  {s.verbrauch_kw != null ? fmtZahl(s.verbrauch_kw, 2) : <Dash />}
                </td>
                <td className={`${ZELLE} text-right tabular-nums font-medium ${
                  s.netto_kw == null
                    ? ''
                    : s.netto_kw >= 0
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-red-600 dark:text-red-400'
                }`}>
                  {s.netto_kw != null
                    ? `${s.netto_kw >= 0 ? '+' : ''}${fmtZahl(s.netto_kw, 2)}`
                    : <Dash />}
                </td>
                <td className={`${ZELLE} text-right tabular-nums text-red-600 dark:text-red-400`}>
                  {s.netzbezug_kw != null && s.netzbezug_kw > 0.005 ? fmtZahl(s.netzbezug_kw, 2) : <Dash />}
                </td>
                <td className={`${ZELLE} text-right tabular-nums text-cyan-600 dark:text-cyan-400`}>
                  {s.einspeisung_kw != null && s.einspeisung_kw > 0.005 ? fmtZahl(s.einspeisung_kw, 2) : <Dash />}
                </td>
                {hatSpeicher && (
                  <td className={`${ZELLE} text-right tabular-nums text-blue-600 dark:text-blue-400`}>
                    {s.soc_prozent != null ? fmtZahl(s.soc_prozent, 1) : <Dash />}
                  </td>
                )}
              </tr>
            ))}
          </TableBody>
          <TableFoot>
            <tr className="border-t-2 border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 font-semibold">
              <td className={`${ZELLE} text-gray-500 dark:text-gray-400`}>kWh</td>
              <td className={`${ZELLE} text-right tabular-nums text-yellow-700 dark:text-yellow-300`}>{fmtZahl(daten.pv_summe_kwh, 1)}</td>
              {zeigtIst && (
                // Summe der bisher gemessenen Stunden — bewusst kein Tages-IST:
                // die künftigen Stunden fehlen darin und sollen es auch.
                <td className={`${ZELLE} text-right tabular-nums font-medium text-gray-700 dark:text-gray-200`}>{fmtZahl(istSumme, 1)}</td>
              )}
              <td className={`${ZELLE} text-right tabular-nums text-gray-700 dark:text-gray-300`}>
                {daten.verbrauch_summe_kwh != null ? fmtZahl(daten.verbrauch_summe_kwh, 1) : <Dash />}
              </td>
              <td className={`${ZELLE} text-right tabular-nums ${
                daten.verbrauch_summe_kwh == null
                  ? ''
                  : daten.pv_summe_kwh - daten.verbrauch_summe_kwh >= 0
                    ? 'text-green-600 dark:text-green-400'
                    : 'text-red-600 dark:text-red-400'
              }`}>
                {daten.verbrauch_summe_kwh != null
                  ? fmtZahl(daten.pv_summe_kwh - daten.verbrauch_summe_kwh, 1)
                  : <Dash />}
              </td>
              <td className={`${ZELLE} text-right tabular-nums text-red-600 dark:text-red-400`}>
                {daten.netzbezug_summe_kwh != null ? fmtZahl(daten.netzbezug_summe_kwh, 1) : <Dash />}
              </td>
              <td className={`${ZELLE} text-right tabular-nums text-cyan-600 dark:text-cyan-400`}>
                {daten.einspeisung_summe_kwh != null ? fmtZahl(daten.einspeisung_summe_kwh, 1) : <Dash />}
              </td>
              {hatSpeicher && <td />}
            </tr>
          </TableFoot>
        </Table>
    </Card>
  )
}

function Dash() {
  return <span className="text-gray-300 dark:text-gray-600">—</span>
}
