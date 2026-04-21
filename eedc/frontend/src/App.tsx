import { lazy, Suspense } from 'react'
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import { useTouchTitleTooltip } from './hooks/useTouchTitleTooltip'

// LiveDashboard eager — ist die Startseite (/)
import LiveDashboard from './pages/LiveDashboard'

// Alle anderen Seiten lazy laden
// Cockpit (Dashboards)
const Dashboard = lazy(() => import('./pages/Dashboard'))
const PVAnlageDashboard = lazy(() => import('./pages/PVAnlageDashboard'))
const EAutoDashboard = lazy(() => import('./pages/EAutoDashboard'))
const WaermepumpeDashboard = lazy(() => import('./pages/WaermepumpeDashboard'))
const SpeicherDashboard = lazy(() => import('./pages/SpeicherDashboard'))
const WallboxDashboard = lazy(() => import('./pages/WallboxDashboard'))
const BalkonkraftwerkDashboard = lazy(() => import('./pages/BalkonkraftwerkDashboard'))
const SonstigesDashboard = lazy(() => import('./pages/SonstigesDashboard'))

// Auswertungen
const Auswertung = lazy(() => import('./pages/Auswertung'))
const ROIDashboard = lazy(() => import('./pages/ROIDashboard'))
const PrognoseVsIst = lazy(() => import('./pages/PrognoseVsIst'))
const MonatsabschlussView = lazy(() => import('./pages/MonatsabschlussView'))

// Aussichten (Prognosen)
const Aussichten = lazy(() => import('./pages/Aussichten'))

// Einstellungen - Stammdaten
const Anlagen = lazy(() => import('./pages/Anlagen'))
const Strompreise = lazy(() => import('./pages/Strompreise'))
const Investitionen = lazy(() => import('./pages/Investitionen'))
const Infothek = lazy(() => import('./pages/Infothek'))

// Einstellungen - Daten
const Monatsdaten = lazy(() => import('./pages/Monatsdaten'))
const Import = lazy(() => import('./pages/Import'))
const Einrichtung = lazy(() => import('./pages/Einrichtung'))
const MqttInboundSetup = lazy(() => import('./pages/MqttInboundSetup'))

// Einstellungen - System & HA
const Backup = lazy(() => import('./pages/Backup'))
const Settings = lazy(() => import('./pages/Settings'))
const PVGISSettings = lazy(() => import('./pages/PVGISSettings'))
const HAExportSettings = lazy(() => import('./pages/HAExportSettings'))
const SensorMappingWizard = lazy(() => import('./pages/SensorMappingWizard'))
const MonatsabschlussWizard = lazy(() => import('./pages/MonatsabschlussWizard'))
const HAStatistikImport = lazy(() => import('./pages/HAStatistikImport'))
const CommunityShare = lazy(() => import('./pages/CommunityShare'))
const Community = lazy(() => import('./pages/Community'))
const DataImportWizard = lazy(() => import('./pages/DataImportWizard'))
const ConnectorSetupWizard = lazy(() => import('./pages/ConnectorSetupWizard'))
const CloudImportWizard = lazy(() => import('./pages/CloudImportWizard'))
const CustomImportWizard = lazy(() => import('./pages/CustomImportWizard'))
const Protokolle = lazy(() => import('./pages/Protokolle'))
const DatenChecker = lazy(() => import('./pages/DatenChecker'))

function App() {
  useTouchTitleTooltip()
  // HashRouter für HA Ingress Support (Ingress-Pfad ist dynamisch)
  return (
    <HashRouter>
      <Suspense fallback={null}>
        <Routes>
          <Route path="/" element={<Layout />}>
            {/* Redirect root to Live Dashboard */}
            <Route index element={<Navigate to="/live" replace />} />

            {/* Cockpit (Dashboards) */}
            <Route path="cockpit" element={<Dashboard />} />
            <Route path="cockpit/pv-anlage" element={<PVAnlageDashboard />} />
            <Route path="cockpit/e-auto" element={<EAutoDashboard />} />
            <Route path="cockpit/waermepumpe" element={<WaermepumpeDashboard />} />
            <Route path="cockpit/speicher" element={<SpeicherDashboard />} />
            <Route path="cockpit/wallbox" element={<WallboxDashboard />} />
            <Route path="cockpit/balkonkraftwerk" element={<BalkonkraftwerkDashboard />} />
            <Route path="cockpit/aktueller-monat" element={<Navigate to="/cockpit/monatsberichte" replace />} />
            <Route path="cockpit/monatsberichte" element={<MonatsabschlussView />} />
            <Route path="cockpit/sonstiges" element={<SonstigesDashboard />} />

            {/* Live Dashboard */}
            <Route path="live" element={<LiveDashboard />} />

            {/* Auswertungen */}
            <Route path="auswertungen" element={<Auswertung />} />
            <Route path="auswertungen/roi" element={<ROIDashboard />} />
            <Route path="auswertungen/prognose" element={<PrognoseVsIst />} />
            <Route path="auswertungen/export" element={<Auswertung />} /> {/* TODO: PDF Export */}

            {/* Aussichten (Prognosen) */}
            <Route path="aussichten" element={<Aussichten />} />

            {/* Community */}
            <Route path="community" element={<Community />} />

            {/* Einstellungen - Stammdaten */}
            <Route path="einstellungen/anlage" element={<Anlagen />} />
            <Route path="einstellungen/strompreise" element={<Strompreise />} />
            <Route path="einstellungen/investitionen" element={<Investitionen />} />
            <Route path="einstellungen/infothek" element={<Infothek />} />
            <Route path="einstellungen/solarprognose" element={<PVGISSettings />} />

            {/* Einstellungen - Daten */}
            <Route path="einstellungen/monatsdaten" element={<Monatsdaten />} />
            <Route path="einstellungen/monatsabschluss" element={<Navigate to="/einstellungen/monatsdaten" replace />} />
            <Route path="monatsabschluss/:anlageId" element={<MonatsabschlussWizard />} />
            <Route path="monatsabschluss/:anlageId/:jahr/:monat" element={<MonatsabschlussWizard />} />
            <Route path="einstellungen/daten-checker" element={<DatenChecker />} />
            <Route path="einstellungen/einrichtung" element={<Einrichtung />} />
            <Route path="einstellungen/import" element={<Import />} />
            <Route path="einstellungen/portal-import" element={<DataImportWizard />} />
            <Route path="einstellungen/cloud-import" element={<CloudImportWizard />} />
            <Route path="einstellungen/custom-import" element={<CustomImportWizard />} />
            <Route path="einstellungen/connector" element={<ConnectorSetupWizard />} />
            <Route path="einstellungen/mqtt-inbound" element={<MqttInboundSetup />} />

            {/* Einstellungen - Home Assistant */}
            <Route path="einstellungen/sensor-mapping" element={<SensorMappingWizard />} />
            <Route path="einstellungen/ha-statistik-import" element={<HAStatistikImport />} />
            <Route path="einstellungen/ha-export" element={<HAExportSettings />} />

            {/* Einstellungen - System */}
            <Route path="einstellungen/backup" element={<Backup />} />
            <Route path="einstellungen/allgemein" element={<Settings />} />
            <Route path="einstellungen/protokolle" element={<Protokolle />} />

            {/* Einstellungen - Community */}
            <Route path="einstellungen/community" element={<CommunityShare />} />

            {/* Redirects für entfernte/umbenannte Seiten */}
            <Route path="einstellungen/datenerfassung" element={<Navigate to="/einstellungen/monatsdaten" replace />} />
            <Route path="einstellungen/demo" element={<Navigate to="/einstellungen/import" replace />} />
            <Route path="einstellungen/ha-import" element={<Navigate to="/einstellungen/monatsdaten" replace />} />
            <Route path="einstellungen/pvgis" element={<Navigate to="/einstellungen/solarprognose" replace />} />
            <Route path="auswertungen/community" element={<Navigate to="/community" replace />} />

            {/* Legacy redirects für alte URLs */}
            <Route path="dashboard" element={<Navigate to="/cockpit" replace />} />
            <Route path="anlagen" element={<Navigate to="/einstellungen/anlage" replace />} />
            <Route path="monatsdaten" element={<Navigate to="/einstellungen/monatsdaten" replace />} />
            <Route path="strompreise" element={<Navigate to="/einstellungen/strompreise" replace />} />
            <Route path="investitionen" element={<Navigate to="/einstellungen/investitionen" replace />} />
            <Route path="auswertung" element={<Navigate to="/auswertungen" replace />} />
            <Route path="roi" element={<Navigate to="/auswertungen/roi" replace />} />
            <Route path="e-auto" element={<Navigate to="/cockpit/e-auto" replace />} />
            <Route path="waermepumpe" element={<Navigate to="/cockpit/waermepumpe" replace />} />
            <Route path="speicher" element={<Navigate to="/cockpit/speicher" replace />} />
            <Route path="wallbox" element={<Navigate to="/cockpit/wallbox" replace />} />
            <Route path="balkonkraftwerk" element={<Navigate to="/cockpit/balkonkraftwerk" replace />} />
            <Route path="sonstiges" element={<Navigate to="/cockpit/sonstiges" replace />} />
            <Route path="import" element={<Navigate to="/einstellungen/import" replace />} />
            <Route path="settings" element={<Navigate to="/einstellungen/allgemein" replace />} />
          </Route>
        </Routes>
      </Suspense>
    </HashRouter>
  )
}

export default App
