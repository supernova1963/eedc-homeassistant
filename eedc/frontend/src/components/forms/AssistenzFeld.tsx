/**
 * AssistenzFeld — ein Zähler-/Preis-Feld mit Erfassungs-Assistenz (Monatsabschluss-V4).
 *
 * Über der SoT-`Input`: (a) Zustands-Badge (gemessen/geschätzt/fehlt/weicht-ab,
 * §4.1), (b) Alternativen nur auf Wunsch (▾ „andere Quelle"), (c) „weicht ab"-
 * Hinweis mit bewusster Übernahme, (d) Plausibilitäts-Warnungen. Ersetzt die
 * frühere Wizard-Mechanik (Placeholder „Vorschlag", Übernehmen-Knopf, 3-Chip-
 * Reihe, P5) durch „vor-ausgefüllt, du prüfst nur die Ausreißer".
 *
 * Prefill selbst macht die Form (Lücken füllen, R1/R2) — dieses Feld VISUALISIERT
 * nur den Zustand des aktuellen Werts und bietet Alternativen an.
 *
 * Design-Hinweis (bewusst): die drei Klick-Affordanzen (▾ „andere Quelle",
 * „Sensorwert übernehmen", Alternativ-Chips) sind schlanke 11-px-Inline-Disclosures
 * (Konzept §4.1: „aufklappbares ▾", NICHT die entfernte Chip-Button-Reihe von P5).
 * Der SoT-`Button` erzwingt min-h-36px und wäre pro Feld zu schwer; `check:buttons`
 * regelt ausschließlich `src/v4`. Bleiben daher bewusst rohe <button> (Freigabe-
 * fähig am Dev-Box-Sicht-Gate).
 */

import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import type { FeldStatus } from '../../api/monatsabschluss'
import { getQuelleLabel } from '../monatsabschluss/helpers'
import { ermittleZustand, besterVorschlag, gleich } from '../../lib/erfassungZustand'
import { STATUS_TEXT_CLASS } from '../../lib/colors'
import { Input, ErfassungZustandBadge } from '../ui'

interface AssistenzFeldProps {
  label: string
  name: string
  value: string
  onChange: (value: string) => void
  feldStatus?: FeldStatus
  step?: string
  min?: string
  placeholder?: string
  hint?: string
  required?: boolean
  error?: string
  onBlur?: () => void
  /** Wrapper-Ref (Pflichtfeld-Scroll-Ziel der Form). */
  containerRef?: (el: HTMLDivElement | null) => void
}

const WARN_KLASSE: Record<string, string> = {
  error: STATUS_TEXT_CLASS.kritisch,
  warning: STATUS_TEXT_CLASS.warnung,
  info: STATUS_TEXT_CLASS.info,
}

export default function AssistenzFeld({
  label, name, value, onChange, feldStatus,
  step = '0.01', min, placeholder, hint, required, error, onBlur, containerRef,
}: AssistenzFeldProps) {
  const [zeigeAlternativen, setZeigeAlternativen] = useState(false)
  const erg = ermittleZustand(value ?? '', feldStatus)
  const best = besterVorschlag(feldStatus?.vorschlaege)
  const hatWert = (value ?? '').trim() !== ''

  // Quell-Zusatz am Badge: geschätzt → Quelle nennen; gemessen nur „(manuell)"
  // wenn von Hand (Kanon-Wireframe: reines „gemessen" ohne Quell-Suffix).
  const quelleLabel =
    erg.zustand === 'geschaetzt'
      ? getQuelleLabel(erg.quelle ?? '')
      : (erg.zustand === 'gemessen' && (erg.quelle === 'manuell' || erg.quelle === 'manual'))
        ? 'manuell'
        : undefined

  // Alternativen = alle Vorschläge außer dem aktuell übernommenen Wert.
  const alternativen = (feldStatus?.vorschlaege ?? []).filter(
    (v) => !(hatWert && gleich(parseFloat(value), v.wert)),
  )

  // Placeholder: liegt ein bester Vorschlag vor, ihn zeigen (falls Feld leer).
  const platzhalter = best ? `Vorschlag: ${best.wert}` : placeholder

  return (
    <div ref={containerRef}>
      <Input
        label={label}
        name={name}
        type="number"
        step={step}
        min={min}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        placeholder={platzhalter}
        required={required}
        error={error}
        hint={hint}
        warnung={(feldStatus?.warnungen?.length ?? 0) > 0 && !error}
      />

      {/* Zustands-Zeile (nur wenn Backend-Feld bekannt und kein harter Formfehler) */}
      {feldStatus && !error && (
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
          <ErfassungZustandBadge zustand={erg.zustand} quelleLabel={quelleLabel} />
          {alternativen.length > 0 && (
            <button
              type="button"
              onClick={() => setZeigeAlternativen((v) => !v)}
              className="inline-flex items-center gap-0.5 text-[11px] text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
            >
              andere Quelle
              <ChevronDown className={`w-3 h-3 transition-transform ${zeigeAlternativen ? 'rotate-180' : ''}`} />
            </button>
          )}
        </div>
      )}

      {/* „Weicht ab": Sensor meldet X, gespeichert Y — bewusste Übernahme. */}
      {erg.weichtAb && (
        <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-orange-600 dark:text-orange-400">
          <span>Sensor meldet {erg.weichtAb.sensorWert} · gespeichert {erg.weichtAb.gespeichert}</span>
          <button
            type="button"
            onClick={() => onChange(String(erg.weichtAb!.sensorWert))}
            className="underline hover:no-underline"
          >
            Sensorwert übernehmen
          </button>
        </div>
      )}

      {/* Alternativen (nur auf Wunsch aufgeklappt) */}
      {zeigeAlternativen && alternativen.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1.5">
          {alternativen.map((v, i) => (
            <button
              key={i}
              type="button"
              title={v.beschreibung}
              onClick={() => { onChange(String(v.wert)); setZeigeAlternativen(false) }}
              className="rounded border border-gray-200 dark:border-gray-700 px-1.5 py-0.5 text-[11px] text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50"
            >
              {v.wert} <span className="text-gray-400 dark:text-gray-500">({getQuelleLabel(v.quelle)})</span>
            </button>
          ))}
        </div>
      )}

      {/* Plausibilitäts-Warnungen (Backend) */}
      {!error && (feldStatus?.warnungen?.length ?? 0) > 0 && (
        <div className="mt-1 space-y-0.5">
          {feldStatus!.warnungen.map((w, i) => (
            <p key={i} className={`text-[11px] ${WARN_KLASSE[w.schwere] ?? STATUS_TEXT_CLASS.info}`}>{w.meldung}</p>
          ))}
        </div>
      )}
    </div>
  )
}
