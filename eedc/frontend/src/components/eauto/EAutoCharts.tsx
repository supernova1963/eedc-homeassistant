/**
 * Geteilte E-Auto-Charts (IST-`EAutoDashboard` + IA-v4-Hub):
 * - {@link EAutoKmVerlauf}: km pro Monat (Bar)
 * - {@link EAutoLadungVerlauf}: Ladung pro Monat nach Quelle (PV/Netz/Extern, gestapelt)
 * - {@link EAutoMonatsTabelle}: km · kWh · PV · Netz · V2H je Monat (Monate „aus Wallbox-Rest"
 *   ohne eigene Zeile gekennzeichnet, N-564)
 * - {@link EAutoKostenvergleich}: E-Auto (Strom) vs. Verbrenner (Benzin) + Ersparnis
 * Eine Code-Wahrheit, kein Drift zwischen Dashboard und Hub.
 */
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import ChartTooltip from '../ui/ChartTooltip'
import { ChartLegende, Table, TableHead, TableBody } from '../ui'
import { ZELLE, KOPF_ZELLE } from '../ui/tabelleMasse'
import { MONAT_KURZ, LADEQUELLEN_FARBEN, GELD_COLORS, GELD_TEXT_CLASS, CHART_COLORS, CHART_HOVER_CURSOR, xAchse, yAchse, achsenEinheit, achsenTick, ACHSEN_MARGIN_TOP, fmtZahl } from '../../lib'
import { useLegendenToggle, useSchmaleAchse } from '../../hooks'
import type { InvestitionMonatsdaten, EAutoDashboardResponse } from '../../api/investitionen'

type Zusammenfassung = EAutoDashboardResponse['zusammenfassung']

/**
 * N-564: eine Zeile, die der Server nur zur Anzeige mitschickt — ein Monat, in dem das Auto
 * Rest der Wallbox bekommt, aber keine eigene Monatszeile hat (Konzept Heimladung Regel 2
 * Schritt 3). Sie trägt `ladung_*`, keine km und keine ID; ohne sie ergäbe die Summe der
 * Tabelle die Kachel „Heimladung" nicht.
 */
export function istRestZeile(md: InvestitionMonatsdaten): boolean {
  return Boolean(md.verbrauch_daten.ladung_aus_rest)
}

/** Tooltip der Rest-Kennzeichnung — ein Wortlaut für Tabelle und Probe. */
export const REST_ZEILE_HINWEIS =
  'Für dieses Auto ist in diesem Monat nichts erfasst. eedc ordnet ihm den Rest der Wallbox zu '
  + '(Wallbox minus die eigenen Messungen der Autos, nach Kilometern verteilt). '
  + 'Kilometer und Fahrverbrauch sind nicht erfasst.'

/**
 * N-555 Stufe 3 (Konzept Heimladung Regel 9): die Heimladung dieses Monats kommt aus den
 * Ladevorgängen des Fahrzeug-Zählers (Sprung je Vorgang, Stunden der Wallbox für Anteil und
 * Monat). Die Notiz nennt ihre Zahl — und wie viele davon die Wallbox nicht voll gezählt hat.
 */
export function ladevorgaengeNotiz(md: InvestitionMonatsdaten): string | null {
  if (!md.verbrauch_daten.ladung_aus_bloecken) return null
  const n = md.verbrauch_daten.ladevorgaenge_bloecke || 0
  const text = n === 1 ? 'aus 1 Ladevorgang' : `aus ${n} Ladevorgängen`
  const ungedeckt = md.verbrauch_daten.ladevorgaenge_ungedeckt || 0
  return ungedeckt > 0 ? `${text}, ${ungedeckt} mit Wallbox-Lücke` : text
}

/** Tooltip der Ladevorgangs-Notiz — ein Wortlaut für Tabelle und Probe. */
export const LADEVORGAENGE_HINWEIS =
  'Menge und PV-Anteil kommen aus den Ladevorgängen des Fahrzeug-Zählers: je Vorgang zählt '
  + 'sein Sprung, die Stunden der Wallbox liefern PV-Anteil und Monat. „Wallbox-Lücke": die '
  + 'Wallbox hat weniger gezählt als das Auto — die Menge bleibt die des Autos.'

/**
 * N-569-Ergänzung (Konzept Heimladung Anhang E): „davon aus dem Speicher" — eine Teilmenge
 * des PV-Anteils (PV = Direkt + Speicher). Nur mit einem Wert über 0; ohne Speicherzähler
 * gibt es keine Zeile.
 */
export function speicherUnterzeile(prozent: number | null | undefined): string | undefined {
  if (prozent == null || prozent <= 0) return undefined
  return `davon aus dem Speicher ${fmtZahl(prozent, 0)} %`
}

/** Monatszeile: „davon aus dem Speicher x kWh" (Teil der Spalte PV), sonst `null`. */
export function speicherNotiz(md: InvestitionMonatsdaten): string | null {
  const kwh = md.verbrauch_daten.ladung_speicher_kwh
  if (!kwh || kwh <= 0) return null
  return `davon ${fmtZahl(kwh, 1)} kWh aus dem Speicher`
}

export function prepEAutoMonate(monatsdaten: InvestitionMonatsdaten[]) {
  return monatsdaten.map((md) => ({
    name: `${MONAT_KURZ[md.monat]} ${md.jahr.toString().slice(2)}`,
    km: md.verbrauch_daten.km_gefahren || 0,
    verbrauch: md.verbrauch_daten.verbrauch_kwh || 0,
    pv: md.verbrauch_daten.ladung_pv_kwh || 0,
    netz: md.verbrauch_daten.ladung_netz_kwh || 0,
    extern: md.verbrauch_daten.ladung_extern_kwh || 0,
    v2h: md.verbrauch_daten.v2h_entladung_kwh || 0,
  }))
}

/** Kilometer pro Monat (Bar). */
export function EAutoKmVerlauf({ monatsdaten }: { monatsdaten: InvestitionMonatsdaten[] }) {
  const schmal = useSchmaleAchse()
  const data = prepEAutoMonate(monatsdaten)
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: ACHSEN_MARGIN_TOP }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" {...xAchse(schmal)} /* achsen-allow: Zeit-/Kategorie-Achse */ />
          <YAxis label={achsenEinheit('km')} tickFormatter={achsenTick} {...yAchse(schmal)} />
          <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip />} />
          <Bar dataKey="km" fill={CHART_COLORS.emobKm} name="km" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Ladung pro Monat nach Quelle (PV/Netz/Extern, gestapelt). */
export function EAutoLadungVerlauf({ monatsdaten }: { monatsdaten: InvestitionMonatsdaten[] }) {
  const schmal = useSchmaleAchse()
  const legende = useLegendenToggle()
  const data = prepEAutoMonate(monatsdaten)
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: ACHSEN_MARGIN_TOP }}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" {...xAchse(schmal)} /* achsen-allow: Zeit-/Kategorie-Achse */ />
          <YAxis label={achsenEinheit('kWh')} tickFormatter={achsenTick} {...yAchse(schmal)} />
          <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip />} />
          <Legend content={<ChartLegende onItemClick={legende.onItemClick} />} />
          <Bar dataKey="pv" stackId="a" fill={LADEQUELLEN_FARBEN.pv} name="Heim: PV" hide={legende.istVersteckt('pv')} />
          <Bar dataKey="netz" stackId="a" fill={LADEQUELLEN_FARBEN.netz} name="Heim: Netz" hide={legende.istVersteckt('netz')} />
          <Bar dataKey="extern" stackId="a" fill={LADEQUELLEN_FARBEN.extern} name="Extern" hide={legende.istVersteckt('extern')} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Kostenvergleich E-Auto (Strom) vs. Verbrenner (Benzin) + Ersparnis-Zeile. */
export function EAutoKostenvergleich({ zusammenfassung: z }: { zusammenfassung: Zusammenfassung }) {
  const data = [
    { name: 'E-Auto (Strom)', value: z.strom_kosten_gesamt_euro || 0, fill: GELD_COLORS.ersparnis },
    { name: 'Verbrenner (Benzin)', value: z.benzin_kosten_alternativ_euro || 0, fill: GELD_COLORS.kosten },
  ]
  return (
    <div className="space-y-2">
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" tickFormatter={(v) => `${fmtZahl(v, 0)} €`} tick={{ fontSize: 10 }} /* achsen-allow: Wert-Achse waagerecht, Einheit/Format pro Tick (de-DE) */ />
            <YAxis type="category" dataKey="name" width={120} tick={{ fontSize: 10 }} /* achsen-allow: Kategorie-Namen */ />
            <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip unit="€" decimals={2} />} />
            <Bar dataKey="value" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="text-center">
        <span className={`text-lg font-semibold ${GELD_TEXT_CLASS.ersparnis}`}>
          Ersparnis: {fmtZahl(z.ersparnis_vs_benzin_euro || 0, 2)} €
        </span>
      </div>
    </div>
  )
}

/** Monatsdaten-Tabelle: km · kWh · PV · Netz · V2H je Monat. */
export function EAutoMonatsTabelle({ monatsdaten }: { monatsdaten: InvestitionMonatsdaten[] }) {
  return (
    <Table>
      <TableHead>
        <tr className="border-b border-gray-200 dark:border-gray-700">
          <th className={`${KOPF_ZELLE} text-left`}>Monat</th>
          <th className={`${KOPF_ZELLE} text-right`}>km</th>
          <th className={`${KOPF_ZELLE} text-right`}>kWh</th>
          <th className={`${KOPF_ZELLE} text-right`}>PV</th>
          <th className={`${KOPF_ZELLE} text-right`}>Netz</th>
          <th className={`${KOPF_ZELLE} text-right`}>V2H</th>
        </tr>
      </TableHead>
      <TableBody>
        {monatsdaten.map((md) => {
          // N-564: Monat ohne eigene Zeile — PV/Netz aus dem Rest der Wallbox, km, Fahrverbrauch
          // und V2H sind nicht erfasst (`—`, A3 Datenlücke). Die Kennzeichnung ist dieselbe
          // leise Zeilen-Notiz wie „· enthält n h" in der Stundentabelle (Regel 0).
          const ausRest = istRestZeile(md)
          const vorgaenge = ladevorgaengeNotiz(md)
          const speicher = speicherNotiz(md)
          return (
            <tr key={md.id ?? `${md.jahr}-${md.monat}`} className="border-b border-gray-100 dark:border-gray-800">
              <td className={ZELLE}>
                {MONAT_KURZ[md.monat]} {md.jahr}
                {ausRest && (
                  <span className="ml-1 text-[10px] font-normal text-gray-400 dark:text-gray-500" title={REST_ZEILE_HINWEIS}>
                    · aus Wallbox-Rest
                  </span>
                )}
                {vorgaenge && (
                  <span className="ml-1 text-[10px] font-normal text-gray-400 dark:text-gray-500" title={LADEVORGAENGE_HINWEIS}>
                    · {vorgaenge}
                  </span>
                )}
                {speicher && (
                  <span className="ml-1 text-[10px] font-normal text-gray-400 dark:text-gray-500">
                    · {speicher}
                  </span>
                )}
              </td>
              <td className={`${ZELLE} text-right`}>{ausRest ? '—' : (md.verbrauch_daten.km_gefahren || 0)}</td>
              <td className={`${ZELLE} text-right`}>{ausRest ? '—' : fmtZahl(md.verbrauch_daten.verbrauch_kwh || 0, 1)}</td>
              <td className={`${ZELLE} text-right text-green-600`}>{fmtZahl(md.verbrauch_daten.ladung_pv_kwh || 0, 1)}</td>
              <td className={`${ZELLE} text-right text-red-600`}>{fmtZahl(md.verbrauch_daten.ladung_netz_kwh || 0, 1)}</td>
              {/* V2H = emobV2h-Identität (cyan), war fälschlich violett (Audit-E). */}
              <td className={`${ZELLE} text-right text-cyan-600`}>{ausRest ? '—' : fmtZahl(md.verbrauch_daten.v2h_entladung_kwh || 0, 1)}</td>
            </tr>
          )
        })}
      </TableBody>
    </Table>
  )
}
