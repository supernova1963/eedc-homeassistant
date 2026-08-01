/**
 * ZustandLegende — das „Muster" der Erfassungs-Zustände für Tester (V4 §5/§6.2).
 *
 * Kleiner ausklappbarer Erklärer unter der Kopf-Ampel: erklärt, was die vier Farben
 * / sechs Zustände bedeuten, damit Status ↔ Daten durchgängig nachvollziehbar sind
 * (Gernot 2026-07-12). Nutzt DIESELBEN Badges wie die Felder — eine Quelle.
 */
import { useState } from 'react'
import { HelpCircle } from 'lucide-react'
import { ErfassungZustandBadge, InlineAktion } from '../ui'
import type { ErfassungZustand } from '../../lib/erfassungZustand'

const EINTRAEGE: { zustand: ErfassungZustand; text: string }[] = [
  { zustand: 'gemessen',   text: 'automatisch vom Sensor / Import' },
  { zustand: 'geprueft',   text: 'von dir eingegeben oder bestätigt — auch eine bewusst behaltene Sensor-Abweichung' },
  { zustand: 'geschaetzt', text: 'Schätzung (Vormonat/Vorjahr) — bitte prüfen, „✓ passt" bestätigt' },
  { zustand: 'weicht_ab',  text: 'Sensor weicht vom gespeicherten Wert ab — noch nicht entschieden' },
  { zustand: 'fehlt',      text: 'erwartet, aber leer (Zähler / gemappter Sensor)' },
  { zustand: 'optional',   text: 'leer, aber nicht nötig — zählt nicht' },
]

export default function ZustandLegende() {
  const [offen, setOffen] = useState(false)
  return (
    <div className="mt-2">
      <InlineAktion ton="neutral" ariaExpanded={offen} onClick={() => setOffen((o) => !o)}>
        <HelpCircle className="w-3 h-3" /> Was bedeuten die Zustände?
      </InlineAktion>
      {offen && (
        <div className="mt-1.5 grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1">
          {EINTRAEGE.map((e) => (
            <div key={e.zustand} className="flex items-center gap-2 text-[11px] text-gray-600 dark:text-gray-300">
              <ErfassungZustandBadge zustand={e.zustand} className="flex-shrink-0" />
              <span className="min-w-0">{e.text}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
