/**
 * MonatBilanz — KPI-Strip-Bauer + Energie-Bilanz-Block der Cockpit/Monat-Sicht
 * (IA v4 E3 Slice 2c).
 *
 * - {@link baueMonatKpis}: der D1-Strip (5 Energie-Cards + Netto-Ertrag €, B3),
 *   Vormonat in der Zweitzeile, SOLL-Annotation am PV-KPI (O2 Teil 1).
 * - {@link MonatBilanz}: IST/Vormonat/Vorjahr/Ø-Monat-Vergleichstabelle (B10) +
 *   schlanker SOLL/IST-Fortschrittsblock (PVGIS, O2 Teil 2). Kein PV-Verteilungs-
 *   Balken (O3 lebt in der Fluss-Linse des Tagesverlaufs).
 *
 * Quellen verhaltensgleich zum Donor `pages/MonatsabschlussView.tsx`: IST + Vorjahr
 * + SOLL aus `aktuellerMonatApi.getData`, Vormonat + Ø-Monat aus der Monatsreihe
 * (`monatsdatenApi.listAggregiert`).
 */
import { fmtCalc } from '../components/ui'
import { Sun, Activity, Zap, ArrowUpFromLine, Plug, Euro } from 'lucide-react'
import type { KpiStripItem } from '../components/blocks'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import type { AggregierteMonatsdaten } from '../api/monatsdaten'

export interface GleicheMonatStats {
  pv: number | null
  ev: number | null
  einsp: number | null
  netz: number | null
  gesamt: number | null
  autarkie: number | null
  count: number
}

const fmt = (v: number | null | undefined, dec = 0) => fmtCalc(v, dec, '—')

/** D1-Strip: 5 Energie + Netto-Ertrag €. Vormonat in der Zweitzeile, SOLL am PV. */
export function baueMonatKpis(
  d: AktuellerMonatResponse,
  vm: AggregierteMonatsdaten | null,
): KpiStripItem[] {
  const pvSoll = d.soll_pv_kwh != null && d.pv_erzeugung_kwh != null
    ? `SOLL ${fmt(d.soll_pv_kwh)} kWh · ${Math.round((d.pv_erzeugung_kwh / d.soll_pv_kwh) * 100)} %`
    : vm ? `VM: ${fmt(vm.pv_erzeugung_kwh)} kWh` : undefined

  return [
    {
      title: 'PV-Erzeugung', value: fmt(d.pv_erzeugung_kwh), unit: 'kWh', color: 'yellow', icon: Sun,
      subtitle: pvSoll,
    },
    {
      title: 'Autarkie', value: fmt(d.autarkie_prozent), unit: '%', color: 'green', icon: Activity,
      subtitle: vm ? `VM: ${fmt(vm.autarkie_prozent)} %` : undefined,
      formel: 'Eigenverbrauch ÷ Gesamtverbrauch × 100',
      berechnung: d.eigenverbrauch_kwh != null && d.gesamtverbrauch_kwh != null
        ? `${fmt(d.eigenverbrauch_kwh)} ÷ ${fmt(d.gesamtverbrauch_kwh)} kWh` : undefined,
      ergebnis: d.autarkie_prozent != null ? `= ${fmtCalc(d.autarkie_prozent, 1)} %` : undefined,
    },
    {
      title: 'Eigenverbrauch', value: fmt(d.eigenverbrauch_kwh), unit: 'kWh', color: 'purple', icon: Zap,
      subtitle: `EV-Quote ${fmt(d.eigenverbrauch_quote_prozent)} %${vm ? ` · VM: ${fmt(vm.eigenverbrauch_kwh)} kWh` : ''}`,
    },
    {
      title: 'Einspeisung', value: fmt(d.einspeisung_kwh), unit: 'kWh', color: 'green', icon: ArrowUpFromLine,
      subtitle: vm ? `VM: ${fmt(vm.einspeisung_kwh)} kWh` : undefined,
    },
    {
      title: 'Netzbezug', value: fmt(d.netzbezug_kwh), unit: 'kWh', color: 'red', icon: Plug,
      subtitle: vm ? `VM: ${fmt(vm.netzbezug_kwh)} kWh` : undefined,
    },
    {
      title: 'Netto-Ertrag', value: fmtCalc(d.netto_ertrag_euro, 2, '—'), unit: '€', color: 'blue', icon: Euro,
    },
  ]
}

function Delta({ a, b, inv = false }: { a: number | null | undefined; b: number | null | undefined; inv?: boolean }) {
  if (a == null || b == null || b === 0) return null
  const pct = ((a - b) / Math.abs(b)) * 100
  const positive = inv ? pct <= 0 : pct >= 0
  return (
    <span className={`text-xs font-medium px-1 py-0.5 rounded ${
      positive
        ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
        : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
    }`}>
      {pct >= 0 ? '▲' : '▼'} {Math.abs(pct).toFixed(0)} %
    </span>
  )
}

interface BilanzRow {
  label: string
  ist: number | null | undefined
  vm: number | null | undefined
  vj: number | null | undefined
  gm: number | null
  unit: string
  inv?: boolean
}

export function MonatBilanz({
  d, vm, glMonStats, monatName,
}: {
  d: AktuellerMonatResponse
  vm: AggregierteMonatsdaten | null
  glMonStats: GleicheMonatStats | null
  monatName: string
}) {
  const vj = d.vorjahr
  const rows: BilanzRow[] = [
    { label: 'PV-Erzeugung',    ist: d.pv_erzeugung_kwh,   vm: vm?.pv_erzeugung_kwh,   vj: vj?.pv_erzeugung_kwh,   gm: glMonStats?.pv ?? null,       unit: 'kWh' },
    { label: 'Eigenverbrauch',  ist: d.eigenverbrauch_kwh,  vm: vm?.eigenverbrauch_kwh, vj: vj?.eigenverbrauch_kwh, gm: glMonStats?.ev ?? null,       unit: 'kWh' },
    { label: 'Einspeisung',     ist: d.einspeisung_kwh,     vm: vm?.einspeisung_kwh,    vj: vj?.einspeisung_kwh,    gm: glMonStats?.einsp ?? null,    unit: 'kWh' },
    { label: 'Netzbezug',       ist: d.netzbezug_kwh,       vm: vm?.netzbezug_kwh,      vj: vj?.netzbezug_kwh,      gm: glMonStats?.netz ?? null,     unit: 'kWh', inv: true },
    { label: 'Gesamtverbrauch', ist: d.gesamtverbrauch_kwh, vm: vm?.gesamtverbrauch_kwh, vj: vj?.gesamtverbrauch_kwh, gm: glMonStats?.gesamt ?? null,  unit: 'kWh' },
    { label: 'Autarkie',        ist: d.autarkie_prozent,    vm: vm?.autarkie_prozent,   vj: vj?.autarkie_prozent,   gm: glMonStats?.autarkie ?? null, unit: '%'   },
  ]

  const dash = <span className="text-gray-300 dark:text-gray-600">—</span>
  const dec = (row: BilanzRow) => (row.unit === '%' ? 1 : 0)

  // Vergleichsspalte als Paar: Wert (dezimalbündig, erst ab sm sichtbar) + Δ%
  // (rechtsbündig). Getrennte Zellen, damit Zahlen zeilenübergreifend fluchten (#4).
  const vglZellen = (val: number | null | undefined, row: BilanzRow) => (
    <>
      <td className="py-1.5 pl-3 text-right tabular-nums text-gray-400 dark:text-gray-500 hidden sm:table-cell">
        {val != null ? fmt(val, dec(row)) : dash}
      </td>
      <td className="py-1.5 pr-1 text-right tabular-nums">
        {val != null ? <Delta a={row.ist} b={val} inv={row.inv} /> : dash}
      </td>
    </>
  )

  const sollPct = d.soll_pv_kwh != null && d.pv_erzeugung_kwh != null && d.soll_pv_kwh > 0
    ? Math.round((d.pv_erzeugung_kwh / d.soll_pv_kwh) * 100)
    : null

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {/* IST/VM/VJ/Ø-Tabelle (B10) */}
      <div className="lg:col-span-2 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-400 dark:text-gray-500 border-b border-gray-100 dark:border-gray-700">
              <th className="text-left pb-1.5 font-medium"><span className="sr-only">Kennzahl</span></th>
              {/* Jede Wertspalte überspannt 2 Sub-Spalten (Zahl + Einheit/Δ%), Header zentriert (#4). */}
              <th colSpan={2} className="text-center pb-1.5 font-medium">IST</th>
              <th colSpan={2} className="text-center pb-1.5 font-medium">Vormonat</th>
              <th colSpan={2} className="text-center pb-1.5 font-medium">Vorjahr</th>
              {glMonStats && <th colSpan={2} className="text-center pb-1.5 font-medium">Ø {monatName}</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label} className="border-b border-gray-100 dark:border-gray-700/50 last:border-0">
                <td className="py-1.5 text-gray-600 dark:text-gray-400">{row.label}</td>
                {/* IST: Zahl rechtsbündig + Einheit als eigene linksbündige Spalte. */}
                <td className="py-1.5 pl-3 text-right font-semibold text-gray-900 dark:text-white tabular-nums">
                  {fmt(row.ist, dec(row))}
                </td>
                <td className="py-1.5 pr-1 text-left text-gray-500 dark:text-gray-400">{row.unit}</td>
                {vglZellen(row.vm, row)}
                {vglZellen(row.vj, row)}
                {glMonStats && vglZellen(row.gm, row)}
              </tr>
            ))}
          </tbody>
        </table>
        {glMonStats && (
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-1.5">
            Ø aus {glMonStats.count} {monatName}-Monat{glMonStats.count !== 1 ? 'en' : ''}
          </p>
        )}
      </div>

      {/* SOLL/IST-Fortschritt (PVGIS, O2) */}
      <div>
        {sollPct != null ? (
          <>
            <p className="text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-2">IST/SOLL (PVGIS)</p>
            <div className="flex justify-end">
              <span className={`text-4xl font-bold ${
                sollPct >= 100 ? 'text-green-500 dark:text-green-400'
                  : sollPct >= 75 ? 'text-yellow-500 dark:text-yellow-400'
                  : 'text-orange-500'
              }`}>{sollPct} %</span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 mt-2">
              <div
                className={`h-2 rounded-full ${
                  sollPct >= 100 ? 'bg-green-500' : sollPct >= 75 ? 'bg-yellow-400' : 'bg-orange-400'
                }`}
                style={{ width: `${Math.min(100, sollPct)}%` }}
              />
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1.5">
              {fmt(d.pv_erzeugung_kwh)} von {fmt(d.soll_pv_kwh)} kWh
            </p>
          </>
        ) : (
          <p className="text-xs text-gray-400 dark:text-gray-500">Keine PVGIS-SOLL-Prognose für diesen Monat.</p>
        )}
      </div>
    </div>
  )
}
