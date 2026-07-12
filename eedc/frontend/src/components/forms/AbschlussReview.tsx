/**
 * AbschlussReview — das Tor des „Abschlusses" (V4 §6.6, F3), kein eigener Schritt.
 *
 * Zeigt Prüfergebnisse: Vollständigkeit (Kopf-Ampel-Zählung) + Plausibilität (die
 * `warnungen`, die der Backend-Status ohnehin pro Feld liefert — kein Voll-Checker).
 * Weiches Tor: primär „Speichern & abschließen" (in der Aktionsleiste); harte Fehler
 * (schwere==='error', z. B. negative Zähler) bleiben blockierend, weiche Warnungen
 * nennen das Feld + „zum Feld"-Sprung.
 */
import { AlertTriangle } from 'lucide-react'
import { FormSection, ErfassungZustandBadge } from '../ui'
import type { AmpelZaehlung, ErfassungZustand } from '../../lib/erfassungZustand'
import { STATUS_TEXT_CLASS, ERFASSUNG_ZUSTAND } from '../../lib/colors'

export interface ReviewWarnung {
  feld: string
  feldLabel: string
  meldung: string
  schwere: string // 'error' | 'warning' | 'info'
  /** true = Basis-/Zählerfeld (per-Feld anspringbar); false = Investitionsfeld. */
  basis: boolean
}

const WARN_KLASSE: Record<string, string> = {
  error: STATUS_TEXT_CLASS.kritisch,
  warning: STATUS_TEXT_CLASS.warnung,
  info: STATUS_TEXT_CLASS.info,
}

export default function AbschlussReview({
  ampel,
  warnungen,
  onSpringeZuFeld,
}: {
  ampel: AmpelZaehlung
  warnungen: ReviewWarnung[]
  onSpringeZuFeld: (feld: string) => void
}) {
  const harteFehler = warnungen.filter((w) => w.schwere === 'error')
  const gesamt: ErfassungZustand =
    ampel.offen > 0 ? 'fehlt' : ampel.pruefen > 0 ? 'geschaetzt' : 'gemessen'
  const gesamtLabel =
    ampel.offen > 0 ? `${ampel.offen} offen`
    : ampel.pruefen > 0 ? `${ampel.pruefen} zu prüfen`
    : 'bereit zum Abschluss'

  return (
    <FormSection
      variant="erweitert"
      title="Zusammenfassung ansehen"
      defaultOpen={ampel.offen > 0 || warnungen.length > 0}
      statusSlot={<ErfassungZustandBadge zustand={gesamt} label={gesamtLabel} />}
    >
      <div className="space-y-3">
        <p className="text-sm">
          <span className={ERFASSUNG_ZUSTAND.gemessen.text}>{ampel.fertig} fertig</span>
          <span className="text-gray-400 dark:text-gray-500"> · </span>
          <span className={ERFASSUNG_ZUSTAND.geschaetzt.text}>{ampel.pruefen} zu prüfen</span>
          <span className="text-gray-400 dark:text-gray-500"> · </span>
          <span className={ERFASSUNG_ZUSTAND.fehlt.text}>{ampel.offen} offen</span>
        </p>

        {harteFehler.length > 0 && (
          <p className={`flex items-center gap-1 text-sm ${STATUS_TEXT_CLASS.kritisch}`}>
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            {harteFehler.length} blockierende{harteFehler.length === 1 ? 'r' : ''} Fehler — bitte zuerst korrigieren.
          </p>
        )}

        {warnungen.length > 0 ? (
          <ul className="space-y-1.5">
            {warnungen.map((w, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-x-2 text-sm">
                <span className={`font-medium ${WARN_KLASSE[w.schwere] ?? STATUS_TEXT_CLASS.info}`}>
                  {w.feldLabel}:
                </span>
                <span className="text-gray-600 dark:text-gray-300">{w.meldung}</span>
                {w.basis && (
                  <button
                    type="button"
                    onClick={() => onSpringeZuFeld(w.feld)}
                    className="text-xs text-primary-600 hover:underline dark:text-primary-400"
                  >
                    zum Feld
                  </button>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Keine Plausibilitäts-Auffälligkeiten. Mit „Speichern &amp; abschließen" fertigstellen.
          </p>
        )}
      </div>
    </FormSection>
  )
}
