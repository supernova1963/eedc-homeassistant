/**
 * Einrichtung – Hub-Seite für Datenquellen-Setup
 *
 * Zentrale Übersicht aller Datenimport-Methoden:
 * Geräte-Connector, Portal-Import, Cloud-Import, CSV/JSON Import/Export
 */

import { useNavigate } from 'react-router-dom'
import { Database, Cpu, FileSpreadsheet, Cloud, Upload, Table2, Radio, Network, ChevronRight, CheckCircle2, Circle } from 'lucide-react'
import { useSelectedAnlage, useApiData } from '../hooks'
import { useHAAvailable } from '../hooks/useHAAvailable'
import { connectorApi } from '../api/connector'
import { useWizardHost, type WizardKey } from '../v4/wizardHost'

interface DatenquelleCard {
  title: string
  description: string
  icon: typeof Cpu
  href: string
  /** Overlay-Ziel (Teil D): im Wizard-Host öffnet die Karte diesen Wizard statt
   *  per `navigate` in eine V3-Route zu springen (Dead-End unterm Flag).
   *  Entfällt, wenn das Ziel eine V4-Fläche statt eines Wizards ist (→ `v4Route`). */
  wizard?: WizardKey
  /** V4-Ziel ohne Wizard (B7): Karte schließt das Overlay und navigiert dorthin. */
  v4Route?: string
  /** Karte gilt nur in einer der beiden Welten (B7): die HA-/MQTT-Wizards sind in
   *  V4 zur Datenquellen-Fläche verschmolzen, in V3 bleiben sie bis zum Flip. */
  nur?: 'v3' | 'v4'
  color: string
  bgColor: string
  haOnly?: boolean
}

const datenquellen: DatenquelleCard[] = [
  // B7 (Datenquellen-V4 §2g): in V4 ersetzt die feld-zentrische Fläche die beiden
  // Alt-Wizards „HA Sensor-Zuordnung" + „MQTT-Inbound" — eine Karte statt zwei, die
  // aufs selbe Ziel zeigen. NICHT haOnly: die MQTT-Seite trägt den Standalone-Pfad.
  {
    title: 'Datenquellen',
    description: 'Jedem eedc-Feld seine Quelle zuordnen: Home-Assistant-Sensor oder MQTT (Inbound-Topic bzw. eigenes Broker-Topic).',
    icon: Network,
    href: '/einstellungen/datenquellen',
    v4Route: '/einstellungen/datenquellen',
    nur: 'v4',
    color: 'text-green-600 dark:text-green-400',
    bgColor: 'bg-green-50 dark:bg-green-900/20',
  },
  {
    title: 'HA Sensor-Zuordnung',
    nur: 'v3',
    description: 'Home Assistant Sensoren den eedc-Feldern zuordnen. Monatswerte werden automatisch aus der HA-Statistik-Datenbank gelesen.',
    icon: Database,
    // Alt-1 (Gernot 2026-07-11): V3-href korrigiert — zeigte historisch auf
    // `ha-export` (= MQTT-Export-Seite). Jetzt deckungsgleich mit Titel + Wizard.
    href: '/einstellungen/sensor-mapping',
    color: 'text-green-600 dark:text-green-400',
    bgColor: 'bg-green-50 dark:bg-green-900/20',
    haOnly: true,
  },
  {
    title: 'Geräte-Connector',
    description: 'Direkte Verbindung zu lokalen Geräten (SMA, Fronius, Shelly, etc.) per REST-API. Automatische Zählerstandserfassung.',
    icon: Cpu,
    href: '/einstellungen/connector',
    wizard: 'connector',
    color: 'text-blue-600 dark:text-blue-400',
    bgColor: 'bg-blue-50 dark:bg-blue-900/20',
  },
  {
    title: 'Portal-Import',
    description: 'CSV-Dateien von Hersteller-Portalen importieren: SMA Sunny Portal, SMA eCharger, EVCC, Fronius Solarweb.',
    icon: FileSpreadsheet,
    href: '/einstellungen/portal-import',
    wizard: 'portal-import',
    color: 'text-emerald-600 dark:text-emerald-400',
    bgColor: 'bg-emerald-50 dark:bg-emerald-900/20',
  },
  {
    title: 'Cloud-Import',
    description: 'Historische Daten direkt von Cloud-APIs abrufen: SolarEdge, Fronius, Huawei, Growatt, EcoFlow, Deye/Solarman.',
    icon: Cloud,
    href: '/einstellungen/cloud-import',
    wizard: 'cloud-import',
    color: 'text-violet-600 dark:text-violet-400',
    bgColor: 'bg-violet-50 dark:bg-violet-900/20',
  },
  {
    title: 'Eigene Datei importieren',
    description: 'Beliebige CSV- oder JSON-Dateien importieren: Spalten flexibel den eedc-Feldern zuordnen. Mapping als Template speichern.',
    icon: Table2,
    href: '/einstellungen/custom-import',
    wizard: 'custom-import',
    color: 'text-rose-600 dark:text-rose-400',
    bgColor: 'bg-rose-50 dark:bg-rose-900/20',
  },
  {
    title: 'MQTT-Inbound',
    nur: 'v3',
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
    wizard: 'csv-import',
    color: 'text-amber-600 dark:text-amber-400',
    bgColor: 'bg-amber-50 dark:bg-amber-900/20',
  },
]

export default function Einrichtung() {
  const navigate = useNavigate()
  // Teil D (D1): im Overlay-Host öffnen die Karten den jeweiligen Wizard im
  // selben Overlay (Cross-Wizard, kein navigate-Dead-End); Standalone-Route (V3)
  // behält das navigate-Verhalten. (Alt-1 2026-07-11: das V3-`href` der Karte
  // „HA Sensor-Zuordnung" zeigte historisch auf `ha-export` = MQTT-Export —
  // korrigiert auf `sensor-mapping`, deckungsgleich mit Titel + Wizard.)
  const host = useWizardHost()
  const { selectedAnlageId } = useSelectedAnlage()
  const haAvailable = useHAAvailable()
  const { data: connectorStatus } = useApiData(
    () => connectorApi.getStatus(selectedAnlageId!),
    [selectedAnlageId],
    { enabled: selectedAnlageId != null },
  )

  return (
    <div className="p-4 sm:p-6 max-w-4xl mx-auto space-y-6">
      <div>
        <p className="mt-1 text-gray-600 dark:text-gray-400">
          Richte deine Datenquellen ein, um Monatswerte automatisch oder per Import zu erfassen.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {datenquellen
          .filter(q => !q.haOnly || haAvailable)
          // B7: `imOverlay` ist in dieser Datei der etablierte V3/V4-Diskriminator —
          // die Ersteinrichtung erreicht V4 ausschließlich als Overlay-Wizard.
          .filter(q => !q.nur || (q.nur === 'v4') === host.imOverlay)
          .map((quelle) => {
          const Icon = quelle.icon
          const isConnector = quelle.href === '/einstellungen/connector'
          const isConfigured = isConnector && connectorStatus?.configured

          return (
            <button
              key={quelle.href}
              onClick={() => {
                // V3-Route: unverändertes navigate-Verhalten.
                if (!host.imOverlay) return navigate(quelle.href)
                // V4-Overlay: Wizard im selben Overlay (Cross-Wizard, kein Dead-End)…
                if (quelle.wizard) return host.oeffneWizard(quelle.wizard)
                // …oder V4-Fläche (B7): die ist keine Overlay-Seite → Overlay schließen.
                host.schliessen()
                navigate(quelle.v4Route!)
              }}
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
                    <ChevronRight className="h-4 w-4 text-gray-400 dark:text-gray-500 group-hover:text-gray-600 dark:group-hover:text-gray-300 transition-colors shrink-0" />
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
                          <Circle className="h-3.5 w-3.5 text-gray-400 dark:text-gray-500" />
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
