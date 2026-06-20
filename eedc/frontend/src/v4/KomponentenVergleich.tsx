/**
 * KomponentenVergleich — Block ⑤ „Vergleich" (Pflicht-DÜNN, SPEC-KOMPONENTEN K-B9).
 *
 * Jahresvergleich einer Leitkennzahl: block-lokales „Vergleichsjahr ▾",
 * Diagramm ⇄ Tabelle, Δ% neuestes Jahr vs. Vergleichsjahr. Bewusst schlank —
 * der **volle** Mehrjahres-/Spalten-Vergleich + CSV lebt in Auswertungen/Tabelle
 * (Cross-Link unten). Saison/HDD-Anreicherung (WP) + String-SOLL/IST (PV) sind
 * die spezifische Auflage und kommen später.
 */
import { useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { fmtCalc } from '../components/ui'
import { ExternalLink } from 'lucide-react'

export interface VergleichJahr { jahr: number; summe: number }

export function KomponentenVergleich({
  label, einheit, farbe, jahre,
}: { label: string; einheit: string; farbe: string; jahre: VergleichJahr[] }) {
  const [modus, setModus] = useState<'diagramm' | 'tabelle'>('diagramm')
  const sortiert = [...jahre].sort((a, b) => a.jahr - b.jahr)
  const neuestes = sortiert[sortiert.length - 1]
  const [vglJahr, setVglJahr] = useState<number>(sortiert[sortiert.length - 2]?.jahr ?? neuestes?.jahr)

  if (sortiert.length < 2) {
    return (
      <div className="space-y-2">
        <p className="text-sm text-gray-500 dark:text-gray-400">Jahresvergleich ab dem zweiten vollständigen Jahr verfügbar.</p>
        <Crosslink />
      </div>
    )
  }

  const ref = sortiert.find((j) => j.jahr === vglJahr) ?? sortiert[sortiert.length - 2]
  const deltaPct = ref.summe > 0 ? ((neuestes.summe - ref.summe) / ref.summe) * 100 : null

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
          Vergleichsjahr
          <select
            value={vglJahr} onChange={(e) => setVglJahr(Number(e.target.value))}
            className="min-h-[36px] rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 text-sm"
          >
            {sortiert.filter((j) => j.jahr !== neuestes.jahr).map((j) => (
              <option key={j.jahr} value={j.jahr}>{j.jahr}</option>
            ))}
          </select>
        </label>
        <div className="flex items-center gap-1">
          {(['diagramm', 'tabelle'] as const).map((m) => (
            <button key={m} type="button" onClick={() => setModus(m)}
              className={`min-h-[36px] px-3 rounded-lg text-sm font-medium capitalize ${
                modus === m
                  ? 'bg-primary-100 text-primary-700 dark:bg-primary-900/50 dark:text-primary-300'
                  : 'text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800/50'
              }`}>{m === 'diagramm' ? 'Diagramm' : 'Tabelle'}</button>
          ))}
        </div>
      </div>

      {deltaPct != null && (
        <p className="text-sm text-gray-600 dark:text-gray-300">
          {label} {neuestes.jahr}: <span className="font-semibold">{fmtCalc(neuestes.summe, 0)} {einheit}</span>
          {' '}— {deltaPct >= 0 ? '+' : ''}{fmtCalc(deltaPct, 1)} % vs. {ref.jahr}
        </p>
      )}

      {modus === 'diagramm' ? (
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={sortiert.map((j) => ({ name: String(j.jahr), summe: j.summe }))} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" fontSize={11} />
              <YAxis fontSize={10} width={44} unit={` ${einheit}`} />
              <Tooltip formatter={(v: number) => [`${Math.round(v)} ${einheit}`, label]} />
              <Bar dataKey="summe" name={label}>
                {sortiert.map((j) => (
                  <Cell key={j.jahr} fill={farbe} fillOpacity={j.jahr === neuestes.jahr || j.jahr === ref.jahr ? 1 : 0.45} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-400 dark:text-gray-500 border-b border-gray-200 dark:border-gray-700">
              <th className="py-1 font-medium">Jahr</th>
              <th className="py-1 font-medium text-right">{label} ({einheit})</th>
              <th className="py-1 font-medium text-right">Δ vs. {ref.jahr}</th>
            </tr>
          </thead>
          <tbody>
            {[...sortiert].reverse().map((j) => {
              const d = ref.summe > 0 ? ((j.summe - ref.summe) / ref.summe) * 100 : null
              return (
                <tr key={j.jahr} className={`border-b border-gray-100 dark:border-gray-800 ${j.jahr === neuestes.jahr ? 'font-semibold' : ''}`}>
                  <td className="py-1">{j.jahr}</td>
                  <td className="py-1 text-right tabular-nums">{fmtCalc(j.summe, 0)}</td>
                  <td className="py-1 text-right tabular-nums text-gray-500 dark:text-gray-400">
                    {j.jahr === ref.jahr || d == null ? '—' : `${d >= 0 ? '+' : ''}${fmtCalc(d, 1)} %`}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      <Crosslink />
    </div>
  )
}

function Crosslink() {
  return (
    <a href="#/v4/auswertungen/tabelle" className="inline-flex items-center gap-1 text-sm text-primary-700 dark:text-primary-300 hover:underline">
      <ExternalLink className="h-4 w-4" /> Voller Mehrjahres-Vergleich + Export → Auswertungen / Tabelle
    </a>
  )
}
