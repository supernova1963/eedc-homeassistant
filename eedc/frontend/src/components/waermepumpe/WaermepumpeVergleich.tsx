/**
 * WaermepumpeVergleich — der Monats-/Saison-Vergleich mit JAZ⇄Strom-Toggle
 * (Block ⑤ im IA-v4-Hub UND im IST-`WaermepumpeDashboard`; eine Code-Wahrheit).
 *
 * - Metrik-Umschalter: Strom (kWh) ⇄ JAZ
 * - Achsen-Umschalter: Monate (je Jahr ein Balken pro Monat) ⇄ Saison
 *   (Winter/Heizperiode/Sommer über die ganze Laufzeit aggregiert)
 * - Saison: bei getrennter Strommessung nur Heizung (Warmwasser ausgeklammert);
 *   unvollständige Saisons blass + (n/Σ)-Label.
 * Eigener State (Toggles) — self-contained, daher in beiden Sichten identisch.
 */
import { useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell, LabelList,
} from 'recharts'
import ChartTooltip from '../ui/ChartTooltip'
import { MONAT_KURZ, SAISON_FENSTER, SERIEN_PALETTE } from '../../lib'
import type { InvestitionMonatsdaten } from '../../api/investitionen'

function Toggle({ aktiv, aktivKlasse, onClick, children, title }: {
  aktiv: boolean; aktivKlasse: string; onClick: () => void; children: string; title?: string
}) {
  return (
    <button
      type="button" onClick={onClick} title={title}
      className={`px-3 py-1 transition-colors ${aktiv ? aktivKlasse : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'}`}
    >{children}</button>
  )
}

export function WaermepumpeVergleich({ monatsdaten, hatGetrennteStrom }: {
  monatsdaten: InvestitionMonatsdaten[]; hatGetrennteStrom: boolean
}) {
  const [modus, setModus] = useState<'jaz' | 'strom'>('strom')
  const [achse, setAchse] = useState<'monate' | 'saison'>('monate')
  const [fenster, setFenster] = useState<keyof typeof SAISON_FENSTER>('winter')

  const jahre = [...new Set(monatsdaten.map((md) => md.jahr))].sort((a, b) => a - b)
  const jahrFarben = SERIEN_PALETTE

  // Monatsvergleich: Jan–Dez als Gruppen, je ein Balken pro Jahr.
  const monatData = Array.from({ length: 12 }, (_, i) => {
    const monat = i + 1
    const entry: Record<string, string | number | null> = { name: MONAT_KURZ[monat] }
    for (const jahr of jahre) {
      const md = monatsdaten.find((m) => m.monat === monat && m.jahr === jahr)
      if (md) {
        const waerme = (md.verbrauch_daten.heizenergie_kwh || 0) + (md.verbrauch_daten.warmwasser_kwh || 0)
        const strom = md.verbrauch_daten.stromverbrauch_kwh || 0
        entry[`val_${jahr}`] = modus === 'jaz'
          ? (strom > 0 ? Math.round((waerme / strom) * 100) / 100 : null)
          : (strom > 0 ? Math.round(strom) : null)
      } else {
        entry[`val_${jahr}`] = null
      }
    }
    return entry
  })

  // Saison-Vergleich: Fokus-Fenster über die gesamte Laufzeit zu Saison-Instanzen.
  const cfg = SAISON_FENSTER[fenster]
  const spanntJahr = cfg.monate.some((m) => m < cfg.startMonat)
  const saisonData = (() => {
    if (jahre.length === 0) return []
    const minJ = jahre[0], maxJ = jahre[jahre.length - 1]
    const rows: { name: string; value: number | null; label: string; vollstaendig: boolean }[] = []
    for (let startJahr = minJ - 1; startJahr <= maxJ; startJahr++) {
      let sumStrom = 0, sumWaerme = 0, monateMitDaten = 0
      for (const m of cfg.monate) {
        const kalenderJahr = m >= cfg.startMonat ? startJahr : startJahr + 1
        const md = monatsdaten.find((x) => x.monat === m && x.jahr === kalenderJahr)
        if (!md) continue
        monateMitDaten++
        if (hatGetrennteStrom) {
          sumStrom += md.verbrauch_daten.strom_heizen_kwh || 0
          sumWaerme += md.verbrauch_daten.heizenergie_kwh || 0
        } else {
          sumStrom += md.verbrauch_daten.stromverbrauch_kwh || 0
          sumWaerme += (md.verbrauch_daten.heizenergie_kwh || 0) + (md.verbrauch_daten.warmwasser_kwh || 0)
        }
      }
      if (monateMitDaten === 0) continue
      const vollstaendig = monateMitDaten === cfg.monate.length
      const basisName = spanntJahr
        ? `${String(startJahr % 100).padStart(2, '0')}/${String((startJahr + 1) % 100).padStart(2, '0')}`
        : `${startJahr}`
      const wert = modus === 'jaz'
        ? (sumStrom > 0 ? Math.round((sumWaerme / sumStrom) * 100) / 100 : null)
        : Math.round(sumStrom)
      rows.push({
        name: vollstaendig ? basisName : `${basisName} (${monateMitDaten}/${cfg.monate.length})`,
        value: wert,
        label: wert == null ? '' : (modus === 'jaz' ? wert.toFixed(2) : wert.toLocaleString('de-DE')),
        vollstaendig,
      })
    }
    return rows
  })()

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-end flex-wrap gap-2">
        <div className="flex rounded-lg border border-gray-300 dark:border-gray-600 text-sm overflow-hidden">
          <Toggle aktiv={modus === 'strom'} aktivKlasse="bg-yellow-500 text-white" onClick={() => setModus('strom')}>Strom (kWh)</Toggle>
          <Toggle aktiv={modus === 'jaz'} aktivKlasse="bg-orange-500 text-white" onClick={() => setModus('jaz')}>JAZ</Toggle>
        </div>
        <div className="flex rounded-lg border border-gray-300 dark:border-gray-600 text-sm overflow-hidden">
          <Toggle aktiv={achse === 'monate'} aktivKlasse="bg-purple-500 text-white" onClick={() => setAchse('monate')}>Monate</Toggle>
          <Toggle aktiv={achse === 'saison'} aktivKlasse="bg-purple-500 text-white" onClick={() => setAchse('saison')}>Saison</Toggle>
        </div>
        {achse === 'saison' && (
          <div className="flex rounded-lg border border-gray-300 dark:border-gray-600 text-sm overflow-hidden">
            {(Object.keys(SAISON_FENSTER) as (keyof typeof SAISON_FENSTER)[]).map((key) => (
              <Toggle key={key} aktiv={fenster === key} aktivKlasse="bg-purple-500 text-white"
                onClick={() => setFenster(key)} title={`${SAISON_FENSTER[key].label} (${SAISON_FENSTER[key].bereich})`}>
                {SAISON_FENSTER[key].label}
              </Toggle>
            ))}
          </div>
        )}
      </div>

      {achse === 'saison' && saisonData.length === 0 ? (
        <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-16">
          Keine Daten im Fenster {cfg.label} ({cfg.bereich}).
        </p>
      ) : (
        <div className="h-72 text-gray-700 dark:text-gray-200">
          <ResponsiveContainer width="100%" height="100%">
            {achse === 'monate' ? (
              <BarChart data={monatData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" fontSize={12} />
                <YAxis domain={modus === 'jaz' ? [0, 6] : undefined} />
                <Tooltip content={<ChartTooltip formatter={(v) => modus === 'jaz' ? v?.toFixed(2) : `${v} kWh`} />} />
                <Legend />
                {jahre.map((jahr, i) => (
                  <Bar key={jahr} dataKey={`val_${jahr}`} name={`${jahr}`} fill={jahrFarben[i % jahrFarben.length]} />
                ))}
              </BarChart>
            ) : (
              <BarChart data={saisonData} margin={{ top: 20, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" fontSize={12} />
                <YAxis domain={modus === 'jaz' ? [0, 6] : undefined} />
                <Tooltip content={<ChartTooltip formatter={(v) => modus === 'jaz' ? v?.toFixed(2) : `${v} kWh`} />} />
                <Bar dataKey="value" name={modus === 'jaz' ? 'JAZ' : 'Strom'}>
                  {saisonData.map((s, i) => (
                    <Cell key={i} fill={jahrFarben[i % jahrFarben.length]} fillOpacity={s.vollstaendig ? 1 : 0.4} />
                  ))}
                  <LabelList dataKey="label" position="top" fill="currentColor" fontSize={13} fontWeight={600} />
                </Bar>
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
      )}

      {achse === 'saison' && saisonData.length > 0 && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {cfg.label}: {cfg.bereich} ({cfg.monate.length} Monate).{' '}
          {hatGetrennteStrom
            ? 'Saison-Strom = nur Heizung (Warmwasser ausgeklammert, getrennte Strommessung).'
            : 'Saison-Strom inkl. Warmwasser — keine getrennte Strommessung erfasst.'}{' '}
          Blasse Balken kennzeichnen eine unvollständige Saison.
        </p>
      )}
    </div>
  )
}
