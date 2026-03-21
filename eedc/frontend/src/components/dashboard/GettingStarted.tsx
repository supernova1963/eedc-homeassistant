/**
 * GettingStarted: Willkommens-Karte für neue Nutzer
 */

import { useNavigate } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { Card, Button } from '../../components/ui'

export default function GettingStarted() {
  const navigate = useNavigate()
  return (
    <Card className="bg-primary-50 dark:bg-primary-900/20 border-primary-200 dark:border-primary-800">
      <h2 className="text-lg font-semibold text-primary-900 dark:text-primary-100 mb-4">
        Willkommen bei eedc!
      </h2>
      <p className="text-primary-700 dark:text-primary-300 mb-4">
        Starte mit diesen Schritten, um deine PV-Anlage zu analysieren:
      </p>
      <ol className="list-decimal list-inside text-primary-700 dark:text-primary-300 space-y-2 mb-6">
        <li>Lege deine PV-Anlage unter "Anlagen" an</li>
        <li>Konfiguriere deine Strompreise</li>
        <li>Erfasse Monatsdaten oder importiere eine CSV</li>
        <li>Analysiere deine Ergebnisse in den Auswertungen</li>
      </ol>
      <Button onClick={() => navigate('/einstellungen/anlage')}>
        Jetzt starten
        <ArrowRight className="h-4 w-4 ml-2" />
      </Button>
    </Card>
  )
}
