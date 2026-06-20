/**
 * V4Platzhalter — Platzhalter für IA-v4-Achsen, deren echte Sicht noch nicht
 * gebaut ist (Komponenten/Community/Hilfe/Einstellungen). Hält die Nav vollständig
 * und navigierbar, bis die Sichten nach Phase 3 pattern-treu folgen. Analog zum
 * Platzhalter der noch nicht verdrahteten Cockpit-Zeitsichten in `CockpitV4`.
 */
import { useLocation } from 'react-router-dom'
import { Card } from '../components/ui'

const LABEL: Record<string, string> = {
  komponenten: 'Komponenten',
  auswertungen: 'Auswertungen',
  community: 'Community',
  hilfe: 'Hilfe',
  einstellungen: 'Einstellungen',
}

export default function V4Platzhalter() {
  const { pathname } = useLocation()
  const key = pathname.split('/')[2] ?? ''
  const label = LABEL[key] ?? key

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
      <Card>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Die Achse „{label}" wird nach dem verbindlichen IA-v4-Konzept (Phase 3)
          pattern-treu mit echten Daten gebaut. Bisher ist nur das Referenz-Muster
          Cockpit/Monat ausgearbeitet.
        </p>
      </Card>
    </div>
  )
}
