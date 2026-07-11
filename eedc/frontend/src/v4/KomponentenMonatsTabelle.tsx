/**
 * KomponentenMonatsTabelle — read-only Monats-Detailtabelle (Komponenten-Hub
 * Block ④, IA v4 A.2). Reuse der **selben** `verlauf`-Daten (rows + bars) wie
 * {@link KomponentenVerlaufChart}: eine Datenquelle, kein Drift zwischen Chart
 * und Tabelle. Spalten = Monat + je Serie eine Wertspalte; rechtsbündig,
 * gerundet, neueste zuerst (Regel 0a: Datums-Listen absteigend). Eingeklappt
 * via `<details>` wie die IST-Dashboards („Monatsdaten anzeigen").
 */
import type { VerlaufBar, VerlaufRow } from './KomponentenVerlaufChart'
import { Table, TableHead, TableBody } from '../components/ui/Table'
import { ZELLE, KOPF_ZELLE } from '../components/ui/tabelleMasse'

export function KomponentenMonatsTabelle({
  rows, bars, einheit = 'kWh',
}: { rows: VerlaufRow[]; bars: VerlaufBar[]; einheit?: string }) {
  if (rows.length === 0) return null
  // Neueste zuerst (Regel 0a). `rows` kommt chronologisch aus dem Adapter.
  const zeilen = [...rows].reverse()
  const fmt = (v: number | string | undefined) =>
    typeof v === 'number' ? Math.round(v).toLocaleString('de-DE') : '—'

  return (
    <details className="border-t border-gray-100 dark:border-gray-800 pt-3">
      <summary className="cursor-pointer text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
        Monatsdaten anzeigen ({rows.length})
      </summary>
      <Table aussenClassName="mt-3" flaeche="karte">
          <TableHead>
            <tr className="border-b border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400">
              <th className={`${KOPF_ZELLE} text-left`}>Monat</th>
              {bars.map((b) => (
                <th key={b.key} className={`${KOPF_ZELLE} text-right`}>
                  <span className="inline-flex items-center gap-1.5 justify-end">
                    <span className="inline-block w-2 h-2 rounded-sm shrink-0" style={{ backgroundColor: b.farbe }} />
                    {b.label} <span className="font-normal text-gray-400 dark:text-gray-500">({einheit})</span>
                  </span>
                </th>
              ))}
            </tr>
          </TableHead>
          <TableBody>
            {zeilen.map((r, i) => (
              <tr key={`${r.name}-${i}`} className="border-b border-gray-100 dark:border-gray-800">
                <td className={`${ZELLE} text-gray-700 dark:text-gray-300`}>{r.name}</td>
                {bars.map((b) => (
                  <td key={b.key} className={`${ZELLE} text-right text-gray-900 dark:text-white tabular-nums`}>
                    {fmt(r[b.key])}
                  </td>
                ))}
              </tr>
            ))}
          </TableBody>
        </Table>
    </details>
  )
}
