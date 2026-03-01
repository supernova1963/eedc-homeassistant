import { HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'

// Cockpit (Dashboards)
import Dashboard from './pages/Dashboard'
import PVAnlageDashboard from './pages/PVAnlageDashboard'
import EAutoDashboard from './pages/EAutoDashboard'
import WaermepumpeDashboard from './pages/WaermepumpeDashboard'
import SpeicherDashboard from './pages/SpeicherDashboard'
import WallboxDashboard from './pages/WallboxDashboard'
import BalkonkraftwerkDashboard from './pages/BalkonkraftwerkDashboard'
import SonstigesDashboard from './pages/SonstigesDashboard'

// Auswertungen
import Auswertung from './pages/Auswertung'
import ROIDashboard from './pages/ROIDashboard'
import PrognoseVsIst from './pages/PrognoseVsIst'

// Aussichten (Prognosen)
import Aussichten from './pages/Aussichten'

// Einstellungen - Stammdaten
import Anlagen from './pages/Anlagen'
import Strompreise from './pages/Strompreise'
import Investitionen from './pages/Investitionen'

// Einstellungen - Daten
import Monatsdaten from './pages/Monatsdaten'
import Import from './pages/Import'

// Einstellungen - System
import Backup from './pages/Backup'
import Settings from './pages/Settings'
import PVGISSettings from './pages/PVGISSettings'
import DatenerfassungGuide from './pages/DatenerfassungGuide'
import HAExportSettings from './pages/HAExportSettings'
import SensorMappingWizard from './pages/SensorMappingWizard'
import MonatsabschlussWizard from './pages/MonatsabschlussWizard'
import HAStatistikImport from './pages/HAStatistikImport'
import CommunityShare from './pages/CommunityShare'
import Community from './pages/Community'

function App() {
  // HashRouter für HA Ingress Support (Ingress-Pfad ist dynamisch)
  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          {/* Redirect root to Cockpit */}
          <Route index element={<Navigate to="/cockpit" replace />} />

          {/* Cockpit (Dashboards) */}
          <Route path="cockpit" element={<Dashboard />} />
          <Route path="cockpit/pv-anlage" element={<PVAnlageDashboard />} />
          <Route path="cockpit/e-auto" element={<EAutoDashboard />} />
          <Route path="cockpit/waermepumpe" element={<WaermepumpeDashboard />} />
          <Route path="cockpit/speicher" element={<SpeicherDashboard />} />
          <Route path="cockpit/wallbox" element={<WallboxDashboard />} />
          <Route path="cockpit/balkonkraftwerk" element={<BalkonkraftwerkDashboard />} />
          <Route path="cockpit/sonstiges" element={<SonstigesDashboard />} />

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

          {/* Einstellungen - Daten */}
          <Route path="einstellungen/monatsdaten" element={<Monatsdaten />} />
          <Route path="einstellungen/monatsabschluss" element={<MonatsabschlussWizard />} />
          <Route path="monatsabschluss/:anlageId" element={<MonatsabschlussWizard />} />
          <Route path="monatsabschluss/:anlageId/:jahr/:monat" element={<MonatsabschlussWizard />} />
          <Route path="einstellungen/import" element={<Import />} />
          <Route path="einstellungen/demo" element={<Import />} /> {/* Redirects to Import with demo section */}

          {/* Einstellungen - System */}
          <Route path="einstellungen/backup" element={<Backup />} />
          <Route path="einstellungen/solarprognose" element={<PVGISSettings />} />
          <Route path="einstellungen/pvgis" element={<Navigate to="/einstellungen/solarprognose" replace />} />
          <Route path="einstellungen/datenerfassung" element={<DatenerfassungGuide />} />
          <Route path="einstellungen/ha-import" element={<Navigate to="/einstellungen/datenerfassung" replace />} />
          <Route path="einstellungen/ha-export" element={<HAExportSettings />} />
          <Route path="einstellungen/sensor-mapping" element={<SensorMappingWizard />} />
          <Route path="einstellungen/ha-statistik-import" element={<HAStatistikImport />} />
          <Route path="einstellungen/allgemein" element={<Settings />} />
          <Route path="einstellungen/community" element={<CommunityShare />} />
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
    </HashRouter>
  )
}

export default App
