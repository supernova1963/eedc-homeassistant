/**
 * MonatStepper — schwebende „Player"-Monatsauswahl der Cockpit/Monat-Sicht (mobil).
 *
 * Hybrid zur {@link MonatsRail} (detLAN-Vorschlag 2026-06-19): Desktop behält die
 * Rail (Sidebar mit PV-Balken), mobil ersetzt dieser kompakte, sticky Stepper die
 * horizontale Chip-Leiste. Steuerung wie ein flacher Player:
 *   |◀ ältester · ◀◀ −1 Jahr · ◀ −1 Monat · [Monat ▾ → Liste] · ▶ +1 Monat · ▶▶ +1 Jahr · ▶| neuester
 * Antippbare Mitte öffnet die volle Monatsliste (mit PV-Wert/„läuft"), sodass der
 * Schnell-Sprung erhalten bleibt. Buttons ohne Ziel sind deaktiviert (an den Rändern).
 */
import { useMemo, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import { ChevronFirst, ChevronsLeft, ChevronLeft, ChevronRight, ChevronsRight, ChevronLast, ChevronDown } from 'lucide-react'
import { MONAT_KURZ } from '../lib'
import type { RailEintrag } from './MonatsRail'

interface MonatStepperProps {
  entries: RailEintrag[]
  jahr: number
  monat: number
  onSelect: (jahr: number, monat: number) => void
}

const k = (j: number, m: number) => j * 100 + m

export function MonatStepper({ entries, jahr, monat, onSelect }: MonatStepperProps) {
  const [offen, setOffen] = useState(false)
  // Aufsteigend (ältester → neuester) für die Stepper-Logik.
  const asc = useMemo(
    () => [...entries].sort((a, b) => (a.jahr !== b.jahr ? a.jahr - b.jahr : a.monat - b.monat)),
    [entries],
  )
  const idx = asc.findIndex((e) => e.jahr === jahr && e.monat === monat)
  const oldest = asc[0] ?? null
  const newest = asc[asc.length - 1] ?? null
  const prev = idx > 0 ? asc[idx - 1] : null
  const next = idx >= 0 && idx < asc.length - 1 ? asc[idx + 1] : null
  const find = (j: number, m: number) => asc.find((e) => e.jahr === j && e.monat === m) ?? null
  const prevYear = find(jahr - 1, monat)
  const nextYear = find(jahr + 1, monat)
  const aktuell = idx >= 0 ? asc[idx] : null

  const Btn = ({ ziel, icon: Icon, label }: { ziel: RailEintrag | null; icon: LucideIcon; label: string }) => {
    const disabled = !ziel || k(ziel.jahr, ziel.monat) === k(jahr, monat)
    return (
      <button
        type="button"
        disabled={disabled}
        onClick={() => ziel && onSelect(ziel.jahr, ziel.monat)}
        aria-label={label}
        title={label}
        className="flex items-center justify-center h-9 w-8 shrink-0 rounded-md text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors disabled:opacity-30 disabled:cursor-default disabled:hover:bg-transparent"
      >
        <Icon className="h-4 w-4" />
      </button>
    )
  }

  return (
    <div className="lg:hidden sticky top-0 z-20 -mx-3 px-3 pt-1 pb-2 mb-3 bg-gray-50 dark:bg-gray-900">
      <div className="flex items-center gap-0.5 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-1 py-1 shadow-sm">
        <Btn ziel={oldest} icon={ChevronFirst} label="ältester Monat" />
        <Btn ziel={prevYear} icon={ChevronsLeft} label="ein Jahr zurück" />
        <Btn ziel={prev} icon={ChevronLeft} label="voriger Monat" />
        <button
          type="button"
          onClick={() => setOffen((o) => !o)}
          aria-expanded={offen}
          className="flex-1 flex items-center justify-center gap-1.5 h-9 min-w-0 rounded-md text-sm font-semibold text-gray-900 dark:text-white hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors"
        >
          <span className="truncate">{aktuell ? `${MONAT_KURZ[aktuell.monat]} ${aktuell.jahr}` : '—'}</span>
          {aktuell?.laufend && (
            <span className="text-[10px] leading-none px-1 py-0.5 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">läuft</span>
          )}
          <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${offen ? 'rotate-180' : ''}`} />
        </button>
        <Btn ziel={next} icon={ChevronRight} label="nächster Monat" />
        <Btn ziel={nextYear} icon={ChevronsRight} label="ein Jahr vor" />
        <Btn ziel={newest} icon={ChevronLast} label="neuester Monat" />
      </div>

      {offen && (
        <div className="mt-1 max-h-72 overflow-y-auto rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg divide-y divide-gray-100 dark:divide-gray-700/50">
          {[...asc].reverse().map((e) => {
            const sel = e.jahr === jahr && e.monat === monat
            return (
              <button
                key={k(e.jahr, e.monat)}
                type="button"
                onClick={() => { onSelect(e.jahr, e.monat); setOffen(false) }}
                className={`flex w-full items-center justify-between gap-3 px-3 py-2 text-sm transition-colors ${
                  sel
                    ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 font-semibold'
                    : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/40'
                }`}
              >
                <span>{MONAT_KURZ[e.monat]} {e.jahr}</span>
                <span className={`text-xs ${e.laufend ? 'text-emerald-500 dark:text-emerald-400' : 'text-gray-400 dark:text-gray-500 tabular-nums'}`}>
                  {e.laufend ? 'läuft' : `${Math.round(e.pv_kwh)} kWh`}
                </span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
