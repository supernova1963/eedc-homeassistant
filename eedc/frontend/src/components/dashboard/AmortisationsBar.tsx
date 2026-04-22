/**
 * Amortisations-Fortschrittsbalken
 */

import type { CockpitUebersicht } from '../../api/cockpit'
import { FormelTooltip, fmtCalc } from '../ui'

export default function AmortisationsBar({ data }: { data: CockpitUebersicht }) {
  const invest = data.investition_gesamt_euro
  // Kumulierte Gesamtersparnis: alle Komponenten (analog zu jahres_rendite_prozent im Backend)
  const kumuliert = (data.netto_ertrag_euro || 0)
    + (data.wp_ersparnis_euro || 0)
    + (data.emob_ersparnis_euro || 0)
    + (data.bkw_ersparnis_euro || 0)
    + (data.sonstige_netto_euro || 0)
  const progress = Math.min(100, Math.max(0, (kumuliert / invest) * 100))

  let amortJahr: number | null = null
  if (data.anzahl_monate > 0 && kumuliert > 0 && progress < 100) {
    const jaehrlich = kumuliert / (data.anzahl_monate / 12)
    if (jaehrlich > 0) {
      amortJahr = new Date().getFullYear() + Math.ceil((invest - kumuliert) / jaehrlich)
    }
  }

  const jaehrlich = data.anzahl_monate > 0 && kumuliert > 0
    ? kumuliert / (data.anzahl_monate / 12)
    : null

  return (
    <div className="mt-4 p-3 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg">
      <div className="flex justify-between items-center mb-2">
        <FormelTooltip
          sicht="Gesamt-Anlage · IST-Werte realisiert · kumuliert seit Anschaffung"
          formel="Σ realisierte Erträge ÷ Gesamtinvestition × 100"
          berechnung={`${fmtCalc(kumuliert, 0)} € ÷ ${fmtCalc(invest, 0)} € × 100`}
          ergebnis={`= ${progress.toFixed(1)} % über ${data.anzahl_monate} Monate`}
        >
          <span className="text-xs font-medium text-emerald-700 dark:text-emerald-300">
            Amortisationsfortschritt
          </span>
        </FormelTooltip>
        <span className="text-xs text-emerald-600 dark:text-emerald-400">
          {progress.toFixed(1)} % &nbsp;·&nbsp;
          {Math.round(kumuliert).toLocaleString('de')} € von {Math.round(invest).toLocaleString('de')} €
        </span>
      </div>
      <div className="h-3 bg-emerald-200 dark:bg-emerald-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-emerald-500 rounded-full transition-all duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>
      {progress >= 100
        ? <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1 font-medium">✓ Investition vollständig amortisiert!</p>
        : amortJahr && (
          <p className="text-xs text-emerald-600 dark:text-emerald-400 mt-1">
            Voraussichtliche Amortisation: ca. {amortJahr}
          </p>
        )
      }
      {jaehrlich && (
        <p className="text-xs text-emerald-500/70 dark:text-emerald-400/60 mt-1 italic">
          Basis: tatsächlich realisierte Erträge & Kosten
          (Ø {Math.round(jaehrlich).toLocaleString('de')} €/Jahr über {data.anzahl_monate} Monate)
        </p>
      )}
    </div>
  )
}
