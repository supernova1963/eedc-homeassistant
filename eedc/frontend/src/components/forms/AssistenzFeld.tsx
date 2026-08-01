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
 * Design-Hinweis: die Klick-Affordanzen (▾ „andere Quelle", „Sensorwert übernehmen",
 * „✓ passt", Alternativ-Chips) sind schlanke 11-px-Inline-Disclosures (Konzept §4.1:
 * „aufklappbares ▾", NICHT die entfernte Chip-Button-Reihe von P5). Der volle SoT-
 * `Button` erzwingt min-h-36px und wäre pro Feld zu schwer → sie nutzen den schlanken
 * SoT-Baustein {@link InlineAktion} (eine Komponenten-Klasse für die Inline-Gattung).
 */

import { useState } from 'react'
import { ChevronDown, Check } from 'lucide-react'
import type { FeldStatus } from '../../api/monatsabschluss'
import { getQuelleLabel } from '../monatsabschluss/helpers'
import { ermittleZustand, besterVorschlag, gleichWieVorschlag } from '../../lib/erfassungZustand'
import { STATUS_TEXT_CLASS } from '../../lib/colors'
import { Input, ErfassungZustandBadge, InlineAktion } from '../ui'

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
  /** Nutzer hat die Schätzung bewusst bestätigt (✓ passt) → geprüft statt geschätzt. */
  bestaetigt?: boolean
  /** „✓ passt"-Klick: die aktuelle Schätzung als geprüft markieren. */
  onBestaetigen?: () => void
  /** Nur bei Aufmerksamkeit (geschätzt/weicht-ab/offen) Badge+Aktionen zeigen —
   *  ruhige Felder (gemessen/geprüft/optional) bleiben leer (dichtes Inv-Raster). */
  nurBeiAufmerksamkeit?: boolean
}

const WARN_KLASSE: Record<string, string> = {
  error: STATUS_TEXT_CLASS.kritisch,
  warning: STATUS_TEXT_CLASS.warnung,
  info: STATUS_TEXT_CLASS.info,
}

export default function AssistenzFeld({
  label, name, value, onChange, feldStatus,
  step = '0.01', min, placeholder, hint, required, error, onBlur, containerRef, bestaetigt, onBestaetigen,
  nurBeiAufmerksamkeit = false,
}: AssistenzFeldProps) {
  const [zeigeAlternativen, setZeigeAlternativen] = useState(false)
  const erg = ermittleZustand(value ?? '', feldStatus, bestaetigt)
  const best = besterVorschlag(feldStatus?.vorschlaege)
  const hatWert = (value ?? '').trim() !== ''
  // Ruhige Zustände (fertig/optional) → im „nur bei Aufmerksamkeit"-Modus kein Badge.
  const istRuhig = erg.zustand === 'gemessen' || erg.zustand === 'geprueft' || erg.zustand === 'optional'
  const zeigeZustand = !!feldStatus && !error && (!nurBeiAufmerksamkeit || !istRuhig)

  // Quell-Zusatz am Badge: geschätzt → Quelle nennen; geprüft nur „(manuell)"
  // wenn von Hand (reines „gemessen" ohne Quell-Suffix).
  const quelleLabel =
    erg.zustand === 'geschaetzt'
      ? getQuelleLabel(erg.quelle ?? '')
      : (erg.zustand === 'geprueft' && (erg.quelle === 'manuell' || erg.quelle === 'manual'))
        ? 'manuell'
        : undefined

  // Alternativen = alle Vorschläge außer dem aktuell übernommenen Wert. „Bereits
  // übernommen" gilt mit der Genauigkeit des Vorschlags (PN 90128) — sonst böte
  // ein 1-stelliger Sensorvorschlag 2,3 sich neben dem Wert 2,33 als Alternative an.
  const alternativen = (feldStatus?.vorschlaege ?? []).filter(
    (v) => !(hatWert && gleichWieVorschlag(parseFloat(value), v.wert)),
  )

  // Placeholder: liegt ein bester Vorschlag vor, ihn zeigen (falls Feld leer).
  const platzhalter = best ? `Vorschlag: ${best.wert}` : placeholder

  return (
    <div
      ref={containerRef}
      data-feld={name}
      data-erfassung-offen={erg.zustand === 'fehlt' ? 'true' : undefined}
    >
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

      {/* Zustands-Zeile (bei Aufmerksamkeit bzw. immer, je nach Modus) */}
      {zeigeZustand && (
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
          <ErfassungZustandBadge zustand={erg.zustand} quelleLabel={quelleLabel} />
          {/* „✓ passt": eine Schätzung bewusst als geprüft bestätigen (ohne Wertänderung). */}
          {erg.zustand === 'geschaetzt' && onBestaetigen && (
            <InlineAktion ton="bestaetigen" onClick={onBestaetigen}>
              <Check className="w-3 h-3" /> passt
            </InlineAktion>
          )}
          {alternativen.length > 0 && (
            <InlineAktion
              ton="neutral"
              ariaExpanded={zeigeAlternativen}
              onClick={() => setZeigeAlternativen((v) => !v)}
            >
              andere Quelle
              <ChevronDown className={`w-3 h-3 transition-transform ${zeigeAlternativen ? 'rotate-180' : ''}`} />
            </InlineAktion>
          )}
        </div>
      )}

      {/* „Weicht ab": Sensor meldet X, gespeichert Y — bewusst entscheiden (§4.1):
          Sensorwert übernehmen (→ gemessen) ODER gespeicherten behalten (→ geprüft). */}
      {erg.weichtAb && (
        <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-orange-600 dark:text-orange-400">
          <span>Sensor meldet {erg.weichtAb.sensorWert} · gespeichert {erg.weichtAb.gespeichert}</span>
          <InlineAktion ton="warnung" unterstrichen onClick={() => onChange(String(erg.weichtAb!.sensorWert))}>
            Sensorwert übernehmen
          </InlineAktion>
          {onBestaetigen && (
            <InlineAktion ton="bestaetigen" onClick={onBestaetigen}>
              <Check className="w-3 h-3" /> gespeicherten behalten
            </InlineAktion>
          )}
        </div>
      )}

      {/* Alternativen (nur auf Wunsch aufgeklappt) */}
      {zeigeAlternativen && alternativen.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1.5">
          {alternativen.map((v, i) => (
            <InlineAktion
              key={i}
              variant="chip"
              title={v.beschreibung}
              onClick={() => { onChange(String(v.wert)); setZeigeAlternativen(false) }}
            >
              {v.wert} <span className="text-gray-400 dark:text-gray-500">({getQuelleLabel(v.quelle)})</span>
            </InlineAktion>
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
