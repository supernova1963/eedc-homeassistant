/**
 * ChartDatenTabelle — die EINE Tabellen-Ablesung eines Charts (Regel T + B7,
 * Paket CT `docs/KONZEPT-CHART-TABELLEN.md`, abgenommen 2026-07-18).
 *
 * Bekommt die ohnehin vorhandene Chart-Datenreihe (`daten` + Spalten-Defs mit
 * Label/Einheit — dieselbe Struktur, die Legende/Tooltip speisen) und rendert
 * daraus generisch eine `ui/Table`: 1 Zeile je X-Wert, 1 Spalte je Serie,
 * de-DE-Formate, Summenzeile wo sinnvoll, plus `CsvExportButton`. KEINE
 * handgeschriebene Zweit-Tabelle je Chart (Drift-Klasse) — und kein Ersatz für
 * die kuratierten Sicht-Tabellen (`WerteTabelle` bleibt die reiche Analyse-Sicht).
 *
 * Zeilen-Reihenfolge = Chart-Reihenfolge (Verlaufs-Charts: chronologisch
 * aufsteigend). Die Tabelle ist die 1:1-Ablesung des Charts — sie fällt unter
 * die B2-Ausnahme „Verlaufs-Charts (chronologisch)", nicht unter den
 * Datums-Listen-Default absteigend.
 *
 * Zugang: NUR über den Chart-⇄-Tabelle-Umschalter im Fokus-/Vollbild-Overlay
 * ({@link FokusVollbild}); kein Kartenkopf-Icon (Gernot-Entscheid 2026-07-18).
 */
import { useMemo } from 'react'
import { fmtZahl } from '../../lib'
import { exportToCSV } from '../../utils/export'
import { Table, TableBody, TableCell, TableFoot, TableHead, TableHeader, TableRow } from './Table'
import CsvExportButton from './CsvExportButton'

/** Einheiten, deren Spalten-Summe fachlich sinnvoll ist (Mengen, keine Raten). */
const SUMMIERBARE_EINHEITEN = new Set(['kWh', 'km', '€'])

export interface ChartTabelleSpalte {
  /** Feld-Key in den Chart-Daten (`daten[i][key]`). */
  key: string
  /** Serien-Label — identisch zu Legende/Tooltip (Regel D). */
  label: string
  /** Einheit im Header `Label (Einheit)` (B2); weglassen = einheitenlos. */
  einheit?: string
  /** Nachkommastellen der Anzeige (Default 1). CSV bleibt präziser (max. 4 NK). */
  nachkomma?: number
  /** Summenzeile: Default = Einheit ∈ {kWh, km, €}; explizit übersteuerbar
   *  (z. B. `false` für einen kumulierten Zählerstand in kWh). */
  summierbar?: boolean
}

export interface ChartDatenTabelleProps {
  /** Header der X-Spalte (z. B. „Tag", „Monat", „Zeit"). */
  xLabel: string
  /** Feld-Key der X-Spalte in den Chart-Daten. */
  xKey: string
  spalten: ChartTabelleSpalte[]
  /** Die Chart-Datenreihe — GENAU die Zeilen, die auch der Chart rendert.
   *  `object` statt `Record<…>`: Chart-Punkt-Interfaces haben keine Index-Signatur. */
  daten: ReadonlyArray<object>
  /** CSV-Dateiname inkl. `.csv` (z. B. `verlauf-2026-06.csv`). */
  csvDateiname: string
  /** Fachliche Fenstergröße der Tabelle in Zeilen (T2); 24 für Stundentabellen. */
  zeilen?: number
}

const istSummierbar = (s: ChartTabelleSpalte): boolean =>
  s.summierbar ?? (s.einheit != null && SUMMIERBARE_EINHEITEN.has(s.einheit))

const zahlOderNull = (v: unknown): number | null =>
  typeof v === 'number' && Number.isFinite(v) ? v : null

const feld = (row: object, key: string): unknown => (row as Record<string, unknown>)[key]

/** Float-Artefakte kappen, ohne Anzeige-Rundung zu übernehmen (C3/S20-Linie). */
const rund4 = (v: number): number => Math.round(v * 1e4) / 1e4

const headerText = (label: string, einheit?: string): string =>
  einheit ? `${label} (${einheit})` : label

export function ChartDatenTabelle({
  xLabel, xKey, spalten, daten, csvDateiname, zeilen = 12,
}: ChartDatenTabelleProps) {
  // Spalten-Summen einmal rechnen; Summenzeile nur, wenn mind. eine Spalte summiert.
  const summen = useMemo(() => {
    const out = new Map<string, number>()
    for (const s of spalten) {
      if (!istSummierbar(s)) continue
      let sum = 0
      for (const row of daten) sum += zahlOderNull(feld(row, s.key)) ?? 0
      out.set(s.key, sum)
    }
    return out
  }, [spalten, daten])
  const mitFuss = summen.size > 0

  const exportiereCsv = () => {
    const headers = [xLabel, ...spalten.map((s) => headerText(s.label, s.einheit))]
    const rows: (string | number)[][] = daten.map((row) => [
      String(feld(row, xKey) ?? ''),
      ...spalten.map((s) => {
        const v = zahlOderNull(feld(row, s.key))
        return v != null ? rund4(v) : ''
      }),
    ])
    if (mitFuss) {
      rows.push([
        `Σ ${daten.length} ${xLabel}`,
        ...spalten.map((s) => (summen.has(s.key) ? rund4(summen.get(s.key)!) : '')),
      ])
    }
    exportToCSV(headers, rows, csvDateiname)
  }

  return (
    <div className="space-y-2">
      <div className="flex justify-end">
        <CsvExportButton onClick={exportiereCsv} />
      </div>
      <Table zeilen={zeilen} mitFuss={mitFuss}>
        <TableHead>
          <TableRow>
            <TableHeader>{xLabel}</TableHeader>
            {spalten.map((s) => (
              <TableHeader key={s.key} className="text-right">
                {headerText(s.label, s.einheit)}
              </TableHeader>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {daten.map((row, i) => (
            <TableRow key={`${String(feld(row, xKey))}-${i}`}>
              <TableCell className="whitespace-nowrap">{String(feld(row, xKey) ?? '')}</TableCell>
              {spalten.map((s) => (
                <TableCell key={s.key} className="text-right tabular-nums">
                  {fmtZahl(zahlOderNull(feld(row, s.key)), s.nachkomma ?? 1)}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
        {mitFuss && (
          <TableFoot>
            <TableRow>
              <TableCell className="font-medium whitespace-nowrap">Σ</TableCell>
              {spalten.map((s) => (
                <TableCell key={s.key} className="text-right tabular-nums font-medium">
                  {summen.has(s.key) ? fmtZahl(summen.get(s.key)!, s.nachkomma ?? 1) : '—'}
                </TableCell>
              ))}
            </TableRow>
          </TableFoot>
        )}
      </Table>
    </div>
  )
}

export default ChartDatenTabelle
