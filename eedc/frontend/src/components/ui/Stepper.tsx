import { ReactNode } from 'react'
import { CheckCircle2 } from 'lucide-react'

/**
 * Stepper — kanonische Fortschrittsanzeige für Wizards (Style-Guide Teil D, W1).
 *
 * EIN Stepper-SoT statt Pills-vs-Nummern-Wildwuchs (D17-9): nummerierte Kreise +
 * Verbindungslinien, Häkchen bei erledigt. Desktop zeigt alle Schritte mit Titel,
 * Mobil den aktuellen Titel + „n/m" + schmalen Fortschrittsbalken.
 *
 * Zustände: erledigt (grün + Häkchen, klickbar zum Zurückspringen) · aktuell
 * (Akzent-Farbe + Ring + Nr.) · offen (grau + Nr.). Der Akzent ist `primary`
 * (grün, Default); der Setup-Wizard nutzt `amber` für sein bestehendes Chrome.
 */
export interface StepperSchritt {
  /** Sichtbarer Titel des Schritts. */
  titel: string
  /** Optionales Icon (z. B. lucide) — wird im aktuellen Schritt-Titel-Bereich NICHT
   *  gerendert; der Kreis trägt Nummer/Häkchen. Reserviert für kompakte Layouts. */
  icon?: ReactNode
}

interface StepperProps {
  schritte: StepperSchritt[]
  /** Index des aktuellen Schritts (0-basiert). */
  aktuell: number
  /** Farb-Akzent des aktuellen Schritts. `primary` (grün) ist Standard; der Setup-
   *  Wizard nutzt `amber`, um sein Live-Chrome zu erhalten. */
  akzent?: 'primary' | 'amber'
  /** Klick auf einen bereits erledigten Schritt (index < aktuell). Ohne Handler
   *  sind die Kreise reine Anzeige. */
  onSchrittKlick?: (index: number) => void
  className?: string
}

const AKZENT_KREIS: Record<'primary' | 'amber', string> = {
  primary: 'bg-primary-600 text-white ring-4 ring-primary-500/30',
  amber: 'bg-amber-500 text-white ring-4 ring-amber-500/30',
}

const AKZENT_BALKEN: Record<'primary' | 'amber', string> = {
  primary: 'bg-primary-500',
  amber: 'bg-amber-500',
}

export default function Stepper({
  schritte,
  aktuell,
  akzent = 'primary',
  onSchrittKlick,
  className = '',
}: StepperProps) {
  const letzter = schritte.length - 1
  const fortschritt = letzter > 0 ? Math.min(100, Math.max(0, (aktuell / letzter) * 100)) : 0

  return (
    <div className={className}>
      {/* Desktop: alle Schritte mit Kreis + Titel + Verbindungslinie */}
      <div className="hidden md:flex items-center">
        {schritte.map((schritt, index) => {
          const erledigt = index < aktuell
          const istAktuell = index === aktuell
          const klickbar = erledigt && !!onSchrittKlick

          const kreis = (
            <div
              className={`
                w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium
                transition-all duration-300 flex-shrink-0
                ${erledigt
                  ? 'bg-green-500 text-white'
                  : istAktuell
                    ? AKZENT_KREIS[akzent]
                    : 'bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400'
                }
              `}
            >
              {erledigt ? <CheckCircle2 className="w-5 h-5" /> : index + 1}
            </div>
          )

          return (
            <div key={index} className="flex items-center flex-1 last:flex-none">
              <div className="flex items-center min-w-0">
                {klickbar ? (
                  <button
                    type="button"
                    onClick={() => onSchrittKlick(index)}
                    className="flex items-center rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                  >
                    {kreis}
                    <span className="ml-2 text-sm whitespace-nowrap text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
                      {schritt.titel}
                    </span>
                  </button>
                ) : (
                  <>
                    {kreis}
                    <span
                      className={`ml-2 text-sm whitespace-nowrap ${
                        istAktuell
                          ? 'font-medium text-gray-900 dark:text-white'
                          : 'text-gray-500 dark:text-gray-400'
                      }`}
                    >
                      {schritt.titel}
                    </span>
                  </>
                )}
              </div>
              {index < letzter && (
                <div
                  className={`flex-1 h-0.5 mx-4 ${
                    erledigt ? 'bg-green-500' : 'bg-gray-200 dark:bg-gray-700'
                  }`}
                />
              )}
            </div>
          )
        })}
      </div>

      {/* Mobil: aktueller Titel + n/m + Fortschrittsbalken */}
      <div className="md:hidden">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-gray-900 dark:text-white">
            {schritte[aktuell]?.titel}
          </span>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {aktuell + 1}/{schritte.length}
          </span>
        </div>
        <div className="h-1.5 bg-gray-200 dark:bg-gray-700 rounded-sm overflow-hidden">
          <div
            className={`h-full rounded-sm transition-all duration-500 ${AKZENT_BALKEN[akzent]}`}
            style={{ width: `${fortschritt}%` }}
          />
        </div>
      </div>
    </div>
  )
}
