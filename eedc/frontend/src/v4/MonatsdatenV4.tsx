/**
 * MonatsdatenV4 — eigene native V4-Seite für die Monatsdaten-Pflege (schweres
 * Werkzeug, daher eigene V4-Route statt Inline-Block; Plan §Behandlungs-Klassen).
 *
 * Erreichbar aus dem Einstellungen-Katalog (Kategorie „Daten") über einen
 * Starter-Block, der zur V4-ROUTE `/v4/monatsdaten` navigiert — Navigation
 * *innerhalb* V4, kein Dead-End nach V3. Der Inhalt kommt aus den geteilten
 * {@link ../pages/MonatsdatenTeile} (EINE Code-Wahrheit mit der IST-Seite) und
 * sitzt – wie jede V4-Sicht – in einem {@link BlockShell}-Block (gerahmt/klappbar/
 * fokussierbar, identisch zum Strompreise-Block). Die `anlageId` zieht die Seite
 * aus dem globalen Kontext ({@link useSelectedAnlage}), kein `useParams`.
 */
import { Link } from 'react-router-dom'
import { ArrowLeft, Table2 } from 'lucide-react'
import { ViewShell } from './ViewShell'
import { BlockShell, type Block } from '../components/blocks'
import { useSelectedAnlage } from '../hooks'
import { DataLoadingState } from '../components/common'
import { Alert } from '../components/ui'
import { MonatsdatenVerwaltung } from '../pages/MonatsdatenTeile'

/** Kopfleiste: Rücksprung zu den Einstellungen (Kategorie „Daten") + Titel. */
function Kopf() {
  return (
    <div className="flex items-center gap-3 px-3 sm:px-6 py-3 border-b border-gray-200 dark:border-gray-700">
      <Link
        to="/v4/einstellungen/daten"
        className="flex items-center gap-1 text-sm text-gray-500 hover:text-primary-600 dark:text-gray-400 dark:hover:text-primary-400"
      >
        <ArrowLeft className="h-4 w-4" />
        Einstellungen
      </Link>
      <span className="text-gray-300 dark:text-gray-600">/</span>
      <h1 className="text-sm font-semibold text-gray-900 dark:text-white">Monatsdaten</h1>
    </div>
  )
}

export default function MonatsdatenV4() {
  const { selectedAnlageId, loading } = useSelectedAnlage()

  const inhalt = () => {
    if (loading) {
      return <DataLoadingState loading={true} error={null}><div /></DataLoadingState>
    }
    if (selectedAnlageId == null) {
      return (
        <Alert type="warning">
          Bitte lege zuerst eine Anlage an, um Monatsdaten zu erfassen.
        </Alert>
      )
    }
    // Ganze Verwaltung (Toolbar + Tabelle + Modals + Datenverwaltung) in EINEM
    // Block — analog zum Strompreise-Block (StrompreiseVerwaltung im Katalog-Block).
    const bloecke: Block[] = [{
      id: 'monatsdaten',
      title: 'Monatsdaten',
      icon: Table2,
      defaultOpen: true,
      render: () => <MonatsdatenVerwaltung anlageId={selectedAnlageId} />,
    }]
    return <BlockShell persistKey="v4-monatsdaten" bloecke={bloecke} />
  }

  return (
    <ViewShell bar={<Kopf />}>
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        {inhalt()}
      </div>
    </ViewShell>
  )
}
