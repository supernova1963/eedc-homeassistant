/**
 * JahrBilanz — KPI-Strip-Bauer + Energie-Bilanz-Block der Cockpit/Jahr-Sicht
 * (IA-V4 Muster A, Jahr = Variante von Monat mit Jahres-Granularität).
 *
 * Spiegelt {@link MonatBilanz} 1:1 auf Jahresebene:
 * - {@link baueJahrKpis}: Energie-Strip (5 Energie-Cards + Netto-Ertrag € +
 *   Jahresergebnis €), Vorjahr in der Zweitzeile, SOLL-Annotation am PV-KPI.
 * - {@link JahrBilanz}: IST / Vorjahr / Ø-Jahr-Vergleichstabelle + SOLL/IST-
 *   Fortschritt (Σ PVGIS) + PV-Verteilungs-Balken.
 *
 * Quelle = der Jahres-Aggregat-Shape (`baueJahrAlsMonat`, Σ der 12 Monate),
 * identisch zum Monat (gleiche Bauer-Bildsprache). Vergleichs-Chips (Delta/
 * VglChip) aus `MonatBilanz` wiederverwendet (eine SoT-Komponente). Vorjahr/
 * Ø-Jahr = Σ der aggregierten Monatszeilen je Jahr (`jahrVergleichAus`).
 */
import { fmtCalc } from '../components/ui'
import FormelTooltip from '../components/ui/FormelTooltip'
import { VerteilungsBalken, GeraeteHinweis } from '../components/blocks'
import { DATENROLLE, AMPEL_TEXT_CLASS, AMPEL_BG_CLASS, sollIstStufe } from '../lib'
import { Delta, VglChip } from './MonatBilanz'
import { Sun, Activity, Zap, ArrowUpFromLine, Plug, Euro, Wallet } from 'lucide-react'
import type { KpiStripItem } from '../components/blocks'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import type { JahrVergleich } from './JahrAggregat'

const fmt = (v: number | null | undefined, dec = 0) => fmtCalc(v, dec, '—')

/** D1-Strip: 5 Energie + Netto-Ertrag € + Jahresergebnis €. Vorjahr in der
 *  Zweitzeile, SOLL am PV. */
export function baueJahrKpis(d: AktuellerMonatResponse, vj: JahrVergleich | null): KpiStripItem[] {
  const pvSoll = d.soll_pv_kwh != null && d.pv_erzeugung_kwh != null && d.soll_pv_kwh > 0
    ? `SOLL ${fmt(d.soll_pv_kwh)} kWh · ${fmt((d.pv_erzeugung_kwh / d.soll_pv_kwh) * 100)} %`
    : vj?.pv != null ? `VJ: ${fmt(vj.pv)} kWh` : undefined

  // Jahresergebnis = nach Betriebskosten (verhaltensgleich Monat: Gesamt-
  // Nettoertrag − Betriebskosten + Sonstiges). `!= null`, damit 0 € nicht verschwindet.
  const jahresergebnis = d.gesamtnettoertrag_euro != null
    ? d.gesamtnettoertrag_euro - (d.betriebskosten_anteilig_euro ?? 0) + (d.sonstige_netto_euro ?? 0)
    : null

  return [
    { title: 'PV-Erzeugung', value: fmt(d.pv_erzeugung_kwh), unit: 'kWh', color: 'yellow', icon: Sun, subtitle: pvSoll },
    {
      title: 'Autarkie', value: fmt(d.autarkie_prozent), unit: '%', color: 'green', icon: Activity,
      subtitle: vj?.autarkie != null ? `VJ: ${fmt(vj.autarkie)} %` : undefined,
      formel: 'Eigenverbrauch ÷ Gesamtverbrauch × 100',
      berechnung: d.eigenverbrauch_kwh != null && d.gesamtverbrauch_kwh != null
        ? `${fmt(d.eigenverbrauch_kwh)} ÷ ${fmt(d.gesamtverbrauch_kwh)} kWh` : undefined,
      ergebnis: d.autarkie_prozent != null ? `= ${fmtCalc(d.autarkie_prozent, 1)} %` : undefined,
    },
    {
      title: 'Eigenverbrauch', value: fmt(d.eigenverbrauch_kwh), unit: 'kWh', color: 'purple', icon: Zap,
      subtitle: `EV-Quote ${fmt(d.eigenverbrauch_quote_prozent)} %${vj?.ev != null ? ` · VJ: ${fmt(vj.ev)} kWh` : ''}`,
    },
    {
      title: 'Einspeisung', value: fmt(d.einspeisung_kwh), unit: 'kWh', color: 'green', icon: ArrowUpFromLine,
      subtitle: vj?.einsp != null ? `VJ: ${fmt(vj.einsp)} kWh` : undefined,
    },
    {
      title: 'Netzbezug', value: fmt(d.netzbezug_kwh), unit: 'kWh', color: 'red', icon: Plug,
      subtitle: vj?.netz != null ? `VJ: ${fmt(vj.netz)} kWh` : undefined,
    },
    {
      title: 'Netto-Ertrag', value: fmtCalc(d.netto_ertrag_euro, 2, '—'), unit: '€', color: 'blue', icon: Euro,
      subtitle: 'vor Betriebskosten', formel: 'Einspeise-Erlös + Eigenverbrauchs-Ersparnis',
    },
    {
      title: 'Jahresergebnis', value: fmtCalc(jahresergebnis, 2, '—'), unit: '€',
      color: jahresergebnis != null && jahresergebnis < 0 ? 'red' : 'green', icon: Wallet,
      subtitle: 'nach Betriebskosten', formel: 'Gesamt-Nettoertrag − Betriebskosten + Sonstiges',
    },
  ]
}

interface BilanzRow {
  label: string
  ist: number | null | undefined
  vj: number | null
  oj: number | null
  unit: string
  inv?: boolean
  besserVj?: boolean
  besserOj?: boolean
}

export function JahrBilanz({
  d, vj, oj, ojCount,
}: {
  d: AktuellerMonatResponse
  vj: JahrVergleich | null
  oj: JahrVergleich | null
  ojCount: number
}) {
  // Eigenverbrauch-Färbung folgt der Autarkie-Richtung (analog Monat #337).
  const evBesser = (vglAutarkie: number | null | undefined): boolean | undefined =>
    d.autarkie_prozent != null && vglAutarkie != null ? d.autarkie_prozent >= vglAutarkie : undefined
  const rows: BilanzRow[] = [
    { label: 'PV-Erzeugung',    ist: d.pv_erzeugung_kwh,   vj: vj?.pv ?? null,     oj: oj?.pv ?? null,     unit: 'kWh' },
    { label: 'Eigenverbrauch',  ist: d.eigenverbrauch_kwh,  vj: vj?.ev ?? null,     oj: oj?.ev ?? null,     unit: 'kWh',
      besserVj: evBesser(vj?.autarkie), besserOj: evBesser(oj?.autarkie) },
    { label: 'Direktverbrauch', ist: d.direktverbrauch_kwh, vj: vj?.direkt ?? null, oj: oj?.direkt ?? null, unit: 'kWh' },
    { label: 'Einspeisung',     ist: d.einspeisung_kwh,     vj: vj?.einsp ?? null,  oj: oj?.einsp ?? null,  unit: 'kWh' },
    { label: 'Netzbezug',       ist: d.netzbezug_kwh,       vj: vj?.netz ?? null,   oj: oj?.netz ?? null,   unit: 'kWh', inv: true },
    { label: 'Gesamtverbrauch', ist: d.gesamtverbrauch_kwh, vj: vj?.gesamt ?? null, oj: oj?.gesamt ?? null, unit: 'kWh', inv: true },
    { label: 'Autarkie',        ist: d.autarkie_prozent,    vj: vj?.autarkie ?? null, oj: oj?.autarkie ?? null, unit: '%' },
  ]

  const dash = <span className="text-gray-300 dark:text-gray-600">—</span>
  const dec = (row: BilanzRow) => (row.unit === '%' ? 1 : 0)

  const vglZellen = (val: number | null | undefined, row: BilanzRow, besser?: boolean) => (
    <>
      <td className="py-1.5 pl-3 text-right tabular-nums text-gray-400 dark:text-gray-500 hidden sm:table-cell">
        {val != null ? fmt(val, dec(row)) : dash}
      </td>
      <td className="py-1.5 pr-1 text-right tabular-nums">
        {val != null ? <Delta a={row.ist} b={val} inv={row.inv} besser={besser} /> : dash}
      </td>
    </>
  )

  const sollPct = d.soll_pv_kwh != null && d.pv_erzeugung_kwh != null && d.soll_pv_kwh > 0
    ? Math.round((d.pv_erzeugung_kwh / d.soll_pv_kwh) * 100)
    : null

  const pvGeraete = [
    ...(d.komponenten_geraete?.['pv-module'] ?? []),
    ...(d.komponenten_geraete?.['wechselrichter'] ?? []),
  ]

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {/* IST / Vorjahr / Ø-Jahr-Vergleich */}
      <div className="lg:col-span-2">
        {/* Mobil (< sm): gestapelte Karten + Vergleichs-Chips. */}
        <div className="sm:hidden divide-y divide-gray-100 dark:divide-gray-700/50">
          {rows.map((row) => (
            <div key={row.label} className="py-2">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm text-gray-600 dark:text-gray-400 truncate">{row.label}</span>
                <span className="shrink-0 text-sm font-semibold tabular-nums text-gray-900 dark:text-white">
                  {fmt(row.ist, dec(row))} <span className="text-xs font-normal text-gray-500 dark:text-gray-400">{row.unit}</span>
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5 mt-1">
                <VglChip prefix="VJ" lang="Vorjahr" ist={row.ist} val={row.vj} unit={row.unit} dec={dec(row)} inv={row.inv} besser={row.besserVj} />
                {oj && <VglChip prefix="Ø Jahre" lang="Ø übrige Jahre" ist={row.ist} val={row.oj} unit={row.unit} dec={dec(row)} inv={row.inv} besser={row.besserOj} />}
              </div>
            </div>
          ))}
        </div>

        {/* Desktop (≥ sm): aligned Tabelle. */}
        <div className="hidden sm:block overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-400 dark:text-gray-500 border-b border-gray-100 dark:border-gray-700">
                <th className="text-left pb-1.5 font-medium"><span className="sr-only">Kennzahl</span></th>
                <th colSpan={2} className="text-center pb-1.5 font-medium">IST</th>
                <th colSpan={2} className="text-center pb-1.5 font-medium">Vorjahr</th>
                {oj && <th colSpan={2} className="text-center pb-1.5 font-medium">Ø Jahre</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.label} className="border-b border-gray-100 dark:border-gray-700/50 last:border-0">
                  <td className="py-1.5 text-gray-600 dark:text-gray-400">{row.label}</td>
                  <td className="py-1.5 pl-3 text-right font-semibold text-gray-900 dark:text-white tabular-nums">
                    {fmt(row.ist, dec(row))}
                  </td>
                  <td className="py-1.5 pr-1 text-left text-gray-500 dark:text-gray-400">{row.unit}</td>
                  {vglZellen(row.vj, row, row.besserVj)}
                  {oj && vglZellen(row.oj, row, row.besserOj)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {oj && (
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1.5">
            Ø aus {ojCount} {ojCount !== 1 ? 'Jahren' : 'Jahr'}
          </p>
        )}
      </div>

      {/* SOLL/IST-Fortschritt (Σ PVGIS) + PV-Verteilung */}
      <div>
        {sollPct != null ? (
          <>
            <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-2">
              <FormelTooltip
                formel="IST ÷ SOLL × 100"
                berechnung={d.pv_erzeugung_kwh != null && d.soll_pv_kwh != null ? `${fmt(d.pv_erzeugung_kwh)} ÷ ${fmt(d.soll_pv_kwh)} kWh` : undefined}
                ergebnis={`= ${sollPct} %`}
              >
                IST/SOLL (PVGIS)
              </FormelTooltip>
            </p>
            <div className="flex justify-end">
              <span className={`text-4xl font-bold ${AMPEL_TEXT_CLASS[sollIstStufe(sollPct)]}`}>{sollPct} %</span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-sm h-2 mt-2">
              <div
                className={`h-2 rounded-sm ${AMPEL_BG_CLASS[sollIstStufe(sollPct)]}`}
                style={{ width: `${Math.min(100, sollPct)}%` }}
              />
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5">
              {fmt(d.pv_erzeugung_kwh)} von {fmt(d.soll_pv_kwh)} kWh
            </p>
          </>
        ) : (
          <p className="text-xs text-gray-400 dark:text-gray-500">Keine PVGIS-SOLL-Prognose für dieses Jahr.</p>
        )}

        {d.eigenverbrauch_kwh != null && d.einspeisung_kwh != null && (d.pv_erzeugung_kwh ?? 0) > 0 && (
          <div className="mt-4">
            <VerteilungsBalken
              titel="PV-Verteilung"
              segmente={[
                { label: 'Eigenverbr.', wert: d.eigenverbrauch_kwh, farbe: DATENROLLE.eigenverbrauch.bg },
                { label: 'Einspeisung', wert: d.einspeisung_kwh, farbe: DATENROLLE.einspeisung.bg },
              ]}
            />
          </div>
        )}

        {pvGeraete.length >= 2 && (
          <div className="mt-3">
            <GeraeteHinweis label="PV-Erzeugung aus" namen={pvGeraete} />
          </div>
        )}
      </div>
    </div>
  )
}
