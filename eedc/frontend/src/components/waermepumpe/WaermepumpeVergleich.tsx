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
import { ChartLegende, SegmentControl } from '../ui'
import { MONAT_KURZ, SAISON_FENSTER, SERIEN_PALETTE, CHART_HOVER_CURSOR, SERIE_GEDIMMT, xAchse, yAchse, achsenEinheit, achsenTick, ACHSEN_MARGIN_TOP, fmtZahl } from '../../lib'
import type { InvestitionMonatsdaten } from '../../api/investitionen'
import { useLegendenToggle } from '../../hooks'


export function WaermepumpeVergleich({ monatsdaten, hatGetrennteStrom }: {
  monatsdaten: InvestitionMonatsdaten[]; hatGetrennteStrom: boolean
}) {
  const [modus, setModus] = useState<'jaz' | 'strom'>('strom')
  const [achse, setAchse] = useState<'monate' | 'saison'>('monate')
  const [fenster, setFenster] = useState<keyof typeof SAISON_FENSTER>('winter')
  // B7-Legenden-Toggle (Monate-Zweig, Serie = Jahr); Reset bei Modus-/Achsen-Wechsel.
  const legende = useLegendenToggle(`${modus}:${achse}`)

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
    const rows: { name: string; value: number | null; label: string; vollstaendig: boolean; fill: string }[] = []
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
        label: wert == null ? '' : (modus === 'jaz' ? fmtZahl(wert, 2) : wert.toLocaleString('de-DE')),
        vollstaendig,
        // D12-4: Farbe je Saison-Instanz in die Daten → ChartTooltip-Swatch trifft den Balken (sonst SERIE_NEUTRAL-Grau).
        fill: jahrFarben[rows.length % jahrFarben.length],
      })
    }
    return rows
  })()

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-end flex-wrap gap-2">
        <SegmentControl
          ariaLabel="Kennzahl"
          optionen={[{ key: 'strom', label: 'Strom' }, { key: 'jaz', label: 'JAZ' }] as const}
          value={modus}
          onChange={setModus}
        />
        <SegmentControl
          ariaLabel="Achse"
          optionen={[{ key: 'monate', label: 'Monate' }, { key: 'saison', label: 'Saison' }] as const}
          value={achse}
          onChange={setAchse}
        />
        {achse === 'saison' && (
          <SegmentControl
            ariaLabel="Saison-Fenster"
            optionen={(Object.keys(SAISON_FENSTER) as (keyof typeof SAISON_FENSTER)[]).map((key) => ({
              key, label: SAISON_FENSTER[key].label,
              title: `${SAISON_FENSTER[key].label} (${SAISON_FENSTER[key].bereich})`,
            }))}
            value={fenster}
            onChange={setFenster}
          />
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
              <BarChart data={monatData} margin={{ top: ACHSEN_MARGIN_TOP }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" {...xAchse()} /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */ />
                <YAxis domain={modus === 'jaz' ? [0, 6] : undefined} {...yAchse(false)} tickFormatter={achsenTick} label={achsenEinheit(modus === 'jaz' ? 'JAZ' : 'kWh')} />
                <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip formatter={(v) => modus === 'jaz' ? fmtZahl(v, 2) : `${v} kWh`} />} />
                <Legend content={<ChartLegende onItemClick={legende.onItemClick} />} />
                {jahre.map((jahr, i) => (
                  <Bar key={jahr} dataKey={`val_${jahr}`} name={`${jahr}`} fill={jahrFarben[i % jahrFarben.length]} hide={legende.istVersteckt(`val_${jahr}`)} />
                ))}
              </BarChart>
            ) : (
              // D17-4: SoT-Margin wie der Monats-Modus (die früheren left:0/bottom:0-Overrides
              // schnitten die längeren, −45°-gedrehten Saison-Labels „23/24 (3/4)" ab).
              // BEWUSST OHNE Legende: der Saison-Modus ist EINE Serie (JAZ bzw. Strom) mit
              // per-Instanz-Farben je Saison — jede Scheibe/Balken IST über die X-Achse +
              // Wert-Label beschriftet; eine Farb-Legende dazu wäre eine Doppel-Beschriftung
              // (Style-Guide B7). Die Blass-Dimmung erklärt der Fuß-Hinweis. (check:charts
              // erlaubt Einzelserien ohne Legende.)
              <BarChart data={saisonData} margin={{ top: ACHSEN_MARGIN_TOP }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="name" {...xAchse()} /* achsen-allow: Zeit-/Kategorie-Achse (Saison) */ />
                <YAxis domain={modus === 'jaz' ? [0, 6] : undefined} {...yAchse(false)} tickFormatter={achsenTick} label={achsenEinheit(modus === 'jaz' ? 'JAZ' : 'kWh')} />
                <Tooltip cursor={CHART_HOVER_CURSOR} content={<ChartTooltip formatter={(v) => modus === 'jaz' ? fmtZahl(v, 2) : `${v} kWh`} />} />
                <Bar dataKey="value" name={modus === 'jaz' ? 'JAZ' : 'Strom'}>
                  {saisonData.map((s, i) => (
                    <Cell key={i} fill={jahrFarben[i % jahrFarben.length]} fillOpacity={s.vollstaendig ? 1 : SERIE_GEDIMMT} />
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
