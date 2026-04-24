/**
 * Amortisations-Fortschrittsbalken – zwei Sichten untereinander:
 * Gesamtkosten-Sicht vs. Mehrkosten-Sicht (bei Alternativkosten wie WP/E-Auto).
 */

import type { CockpitUebersicht } from '../../api/cockpit'
import { FormelTooltip, fmtCalc } from '../ui'

interface SichtBarProps {
  label: string
  kurzbeschreibung: string
  invest: number
  kumuliert: number
  anzahlMonate: number
  jaehrlich: number | null
  sicht: string
  formel: string
}

function SichtBar({ label, kurzbeschreibung, invest, kumuliert, anzahlMonate, jaehrlich, sicht, formel }: SichtBarProps) {
  const progress = invest > 0 ? Math.min(100, Math.max(0, (kumuliert / invest) * 100)) : 0
  const amortJahr = (invest > 0 && jaehrlich && jaehrlich > 0 && progress < 100)
    ? new Date().getFullYear() + Math.ceil((invest - kumuliert) / jaehrlich)
    : null

  return (
    <div>
      <div className="flex justify-between items-baseline mb-1 gap-2 flex-wrap">
        <FormelTooltip
          sicht={sicht}
          formel={formel}
          berechnung={`${fmtCalc(kumuliert, 0)} € ÷ ${fmtCalc(invest, 0)} € × 100`}
          ergebnis={`= ${progress.toFixed(1)} % über ${anzahlMonate} Monate`}
        >
          <span className="text-xs font-medium text-emerald-700 dark:text-emerald-300 cursor-help">
            {label}
            <span className="text-emerald-500/70 dark:text-emerald-400/60 font-normal"> · {kurzbeschreibung}</span>
          </span>
        </FormelTooltip>
        <span className="text-xs text-emerald-600 dark:text-emerald-400">
          {progress.toFixed(1)} %
          {amortJahr && <> · Break-Even ca. {amortJahr}</>}
          {progress >= 100 && <> · ✓ amortisiert</>}
        </span>
      </div>
      <div className="h-2 bg-emerald-200 dark:bg-emerald-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-emerald-500 rounded-full transition-all duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>
      <p className="text-xs text-emerald-500/70 dark:text-emerald-400/60 mt-0.5">
        {Math.round(kumuliert).toLocaleString('de')} € von {Math.round(invest).toLocaleString('de')} €
      </p>
    </div>
  )
}

export default function AmortisationsBar({ data }: { data: CockpitUebersicht }) {
  const vollkosten = data.investition_vollkosten_euro ?? data.investition_gesamt_euro
  const mehrkosten = data.investition_mehrkosten_euro ?? data.investition_gesamt_euro
  const kumuliert = (data.netto_ertrag_euro || 0)
    + (data.wp_ersparnis_euro || 0)
    + (data.emob_ersparnis_euro || 0)
    + (data.bkw_ersparnis_euro || 0)
    + (data.sonstige_netto_euro || 0)

  const jaehrlich = data.anzahl_monate > 0 && kumuliert > 0
    ? kumuliert / (data.anzahl_monate / 12)
    : null

  const zeigeBeide = mehrkosten > 0 && vollkosten > mehrkosten * 1.001

  return (
    <div className="mt-4 p-3 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg space-y-3">
      <div className="flex justify-between items-baseline">
        <span className="text-xs font-semibold text-emerald-800 dark:text-emerald-200 uppercase tracking-wide">
          Amortisationsfortschritt
        </span>
        {jaehrlich && (
          <span className="text-xs text-emerald-500/80 dark:text-emerald-400/70">
            Ø {Math.round(jaehrlich).toLocaleString('de')} €/Jahr über {data.anzahl_monate} Monate
          </span>
        )}
      </div>

      <SichtBar
        label="Gesamtkosten-Sicht"
        kurzbeschreibung="jeder € zurück"
        invest={vollkosten}
        kumuliert={kumuliert}
        anzahlMonate={data.anzahl_monate}
        jaehrlich={jaehrlich}
        sicht="Gesamt-Anlage · IST-Werte realisiert · Basis: volle Anschaffungskosten"
        formel="Σ realisierte Erträge ÷ Σ Anschaffungskosten × 100"
      />

      {zeigeBeide && (
        <SichtBar
          label="Mehrkosten-Sicht"
          kurzbeschreibung="vs. Alternative (Verbrenner, Gasheizung …)"
          invest={mehrkosten}
          kumuliert={kumuliert}
          anzahlMonate={data.anzahl_monate}
          jaehrlich={jaehrlich}
          sicht="Gesamt-Anlage · IST-Werte realisiert · Basis: Mehrkosten gegenüber Alternativinvestition"
          formel="Σ realisierte Erträge ÷ Σ (Anschaffung − Alternativkosten) × 100"
        />
      )}

      {zeigeBeide && (
        <p className="text-xs text-emerald-500/70 dark:text-emerald-400/60 italic">
          Bei Investitionen mit Alternativkosten (Wärmepumpe vs. Gas, E-Auto vs. Verbrenner) zeigt die Mehrkosten-Sicht
          die ökonomisch fairere Amortisation der Entscheidung.
        </p>
      )}
    </div>
  )
}
