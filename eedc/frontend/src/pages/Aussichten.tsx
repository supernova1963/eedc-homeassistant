/**
 * Aussichten Hauptseite - Tab-Navigation für Prognosen (route-getrieben, B1/E1-P3)
 */
import { useNavigate, useParams } from 'react-router-dom'
import { Sun, ArrowRight } from 'lucide-react'
import { Card, Button, Alert } from '../components/ui'
import { DataLoadingState } from '../components/common'
import { useSelectedAnlage } from '../hooks'
import { KurzfristTab, LangfristTab, TrendTab, FinanzenTab, PrognoseVergleichTab } from './aussichten/index'

type TabType = 'kurzfristig' | 'prognosen' | 'langfristig' | 'trend' | 'finanzen'

const AUSSICHTEN_TABS = ['kurzfristig', 'prognosen', 'langfristig', 'trend', 'finanzen'] as const

export default function Aussichten() {
  const navigate = useNavigate()
  // Aktiver Tab aus der URL (`/aussichten/<tab>`); Default = kurzfristig.
  const { tab } = useParams()
  const activeTab: TabType = (AUSSICHTEN_TABS as readonly string[]).includes(tab ?? '')
    ? (tab as TabType)
    : 'kurzfristig'

  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()

  if (anlagenLoading) {
    return <DataLoadingState loading={true} error={null}><div /></DataLoadingState>
  }

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <Alert type="warning">
          Bitte lege zuerst eine PV-Anlage an.
        </Alert>
      </div>
    )
  }

  // Prüfe ob Anlage Koordinaten hat
  const anlage = anlagen.find(a => a.id === selectedAnlageId)
  const hatKoordinaten = anlage?.latitude && anlage?.longitude

  if (!hatKoordinaten) {
    return (
      <div className="space-y-6">
        <Card className="text-center py-12">
          <Sun className="h-12 w-12 mx-auto text-yellow-500 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
            Standort nicht konfiguriert
          </h3>
          <p className="text-gray-500 dark:text-gray-400 mb-4">
            Für Prognosen werden die Koordinaten der Anlage benötigt.
            <br />
            Bitte konfiguriere den Standort in den Anlagen-Einstellungen.
          </p>
          <Button onClick={() => navigate('/einstellungen/anlage')}>
            Anlage konfigurieren
            <ArrowRight className="h-4 w-4 ml-2" />
          </Button>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Sticky Header mit Anlagen-Filter (nur bei >1 Anlage; Sub-Tab-Leiste
          lebt in der Layout-SubTabs) */}
      {anlagen.length > 1 && (
        <div className="sticky -top-3 sm:-top-6 z-30 bg-gray-50 dark:bg-gray-900 pb-4 -mx-3 sm:-mx-6 px-3 sm:px-6 pt-3 sm:pt-6">
          <div className="flex items-center justify-end gap-2 flex-wrap">
            <select
              value={selectedAnlageId ?? ''}
              onChange={(e) => setSelectedAnlageId(Number(e.target.value))}
              className="input w-auto"
            >
              {anlagen.map((a) => (
                <option key={a.id} value={a.id}>{a.anlagenname}</option>
              ))}
            </select>
          </div>
        </div>
      )}

      {/* Tab-Inhalte */}
      {selectedAnlageId && (
        <>
          {activeTab === 'kurzfristig' && <KurzfristTab anlageId={selectedAnlageId} />}
          {activeTab === 'prognosen' && <PrognoseVergleichTab anlageId={selectedAnlageId} />}
          {activeTab === 'langfristig' && <LangfristTab anlageId={selectedAnlageId} />}
          {activeTab === 'trend' && <TrendTab anlageId={selectedAnlageId} />}
          {activeTab === 'finanzen' && <FinanzenTab anlageId={selectedAnlageId} />}
        </>
      )}
    </div>
  )
}
