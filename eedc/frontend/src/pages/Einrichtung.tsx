/**
 * Einrichtung – Hub-Seite für Datenquellen-Setup
 *
 * Zentrale Übersicht aller Datenimport-Methoden:
 * Geräte-Connector, Portal-Import, Cloud-Import, CSV/JSON Import/Export
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Database, Cpu, FileSpreadsheet, Cloud, Upload, Table2, Radio, ChevronRight, CheckCircle2, Circle } from 'lucide-react'
import { useAnlagen } from '../hooks'
import { useHAAvailable } from '../hooks/useHAAvailable'
import { connectorApi, type ConnectorStatus } from '../api/connector'

interface DatenquelleCard {
  title: string
  description: string
  icon: typeof Cpu
  href: string
  color: string
  bgColor: string
  haOnly?: boolean
}

const datenquellen: DatenquelleCard[] = [
  {
    title: 'HA Sensor-Zuordnung',
    description: 'Home Assistant Sensoren den EEDC-Feldern zuordnen. Monatswerte werden automatisch aus der HA-Statistik-Datenbank gelesen.',
    icon: Database,
    href: '/einstellungen/ha-export',
    color: 'text-green-600 dark:text-green-400',
    bgColor: 'bg-green-50 dark:bg-green-900/20',
    haOnly: true,
  },
  {
    title: 'Geräte-Connector',
    description: 'Direkte Verbindung zu lokalen Geräten (SMA, Fronius, Shelly, etc.) per REST-API. Automatische Zählerstandserfassung.',
    icon: Cpu,
    href: '/einstellungen/connector',
    color: 'text-blue-600 dark:text-blue-400',
    bgColor: 'bg-blue-50 dark:bg-blue-900/20',
  },
  {
    title: 'Portal-Import',
    description: 'CSV-Dateien von Hersteller-Portalen importieren: SMA Sunny Portal, SMA eCharger, EVCC, Fronius Solarweb.',
    icon: FileSpreadsheet,
    href: '/einstellungen/portal-import',
    color: 'text-emerald-600 dark:text-emerald-400',
    bgColor: 'bg-emerald-50 dark:bg-emerald-900/20',
  },
  {
    title: 'Cloud-Import',
    description: 'Historische Daten direkt von Cloud-APIs abrufen: SolarEdge, Fronius, Huawei, Growatt, EcoFlow, Deye/Solarman.',
    icon: Cloud,
    href: '/einstellungen/cloud-import',
    color: 'text-violet-600 dark:text-violet-400',
    bgColor: 'bg-violet-50 dark:bg-violet-900/20',
  },
  {
    title: 'Eigene Datei importieren',
    description: 'Beliebige CSV- oder JSON-Dateien importieren: Spalten flexibel den EEDC-Feldern zuordnen. Mapping als Template speichern.',
    icon: Table2,
    href: '/einstellungen/custom-import',
    color: 'text-rose-600 dark:text-rose-400',
    bgColor: 'bg-rose-50 dark:bg-rose-900/20',
  },
  {
    title: 'MQTT-Inbound',
    description: 'Live-Leistungsdaten via MQTT empfangen. Universelle Datenbrücke für Node-RED, ioBroker, FHEM, openHAB und andere.',
    icon: Radio,
    href: '/einstellungen/mqtt-inbound',
    color: 'text-blue-600 dark:text-blue-400',
    bgColor: 'bg-blue-50 dark:bg-blue-900/20',
  },
  {
    title: 'CSV/JSON Import/Export',
    description: 'Monatsdaten per CSV importieren, Komplett-Backup als JSON erstellen oder wiederherstellen. Demo-Daten laden.',
    icon: Upload,
    href: '/einstellungen/import',
    color: 'text-amber-600 dark:text-amber-400',
    bgColor: 'bg-amber-50 dark:bg-amber-900/20',
  },
]

export default function Einrichtung() {
  const navigate = useNavigate()
  const { anlagen } = useAnlagen()
  const haAvailable = useHAAvailable()
  const [connectorStatus, setConnectorStatus] = useState<ConnectorStatus | null>(null)

  useEffect(() => {
    if (!anlagen || anlagen.length === 0) return
    connectorApi.getStatus(anlagen[0].id).then(setConnectorStatus).catch(() => {})
  }, [anlagen])

  return (
    <div className="p-4 sm:p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
          Datenquellen einrichten
        </h1>
        <p className="mt-1 text-gray-600 dark:text-gray-400">
          Richte deine Datenquellen ein, um Monatswerte automatisch oder per Import zu erfassen.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {datenquellen.filter(q => !q.haOnly || haAvailable).map((quelle) => {
          const Icon = quelle.icon
          const isConnector = quelle.href === '/einstellungen/connector'
          const isConfigured = isConnector && connectorStatus?.configured

          return (
            <button
              key={quelle.href}
              onClick={() => navigate(quelle.href)}
              className="text-left p-5 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-gray-300 dark:hover:border-gray-600 hover:shadow-md transition-all group"
            >
              <div className="flex items-start gap-4">
                <div className={`p-3 rounded-lg ${quelle.bgColor} shrink-0`}>
                  <Icon className={`h-6 w-6 ${quelle.color}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <h3 className="font-semibold text-gray-900 dark:text-white">
                      {quelle.title}
                    </h3>
                    <ChevronRight className="h-4 w-4 text-gray-400 group-hover:text-gray-600 dark:group-hover:text-gray-300 transition-colors shrink-0" />
                  </div>
                  <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
                    {quelle.description}
                  </p>
                  {/* Status-Anzeige für Connector */}
                  {isConnector && connectorStatus && (
                    <div className="mt-2 flex items-center gap-1.5 text-xs">
                      {isConfigured ? (
                        <>
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                          <span className="text-emerald-600 dark:text-emerald-400">
                            {connectorStatus.geraet_name || connectorStatus.connector_id} konfiguriert
                          </span>
                        </>
                      ) : (
                        <>
                          <Circle className="h-3.5 w-3.5 text-gray-400" />
                          <span className="text-gray-500">Nicht konfiguriert</span>
                        </>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
