import { lazy, Suspense } from 'react'
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import { LEGACY_REDIRECTS } from './routes/routeManifest'
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
const Energieprofil = lazy(() => import('./pages/Energieprofil'))
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
const Hilfe = lazy(() => import('./pages/Hilfe'))

// Dev-only Showcase für Style-Guide-Iteration. Page rendert in Production
// nichts, der Code wird vom Bundler aber trotzdem mit ausgeliefert.
// Lazy-Import minimiert das auf einen kleinen separaten Chunk.
const DesignPreview = lazy(() => import('./pages/DesignPreview'))

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
            <Route path="cockpit/monatsberichte" element={<MonatsabschlussView />} />
            <Route path="cockpit/sonstiges" element={<SonstigesDashboard />} />

            {/* Live Dashboard */}
            <Route path="live" element={<LiveDashboard />} />

            {/* Auswertungen — Sub-Tabs route-getrieben (B1). Statische
                Geschwister-Routen (roi/prognose/export) ranken über `:tab`. */}
            <Route path="auswertungen/:tab" element={<Auswertung />} />
            <Route path="auswertungen/roi" element={<ROIDashboard />} />
            <Route path="auswertungen/prognose" element={<PrognoseVsIst />} />
            <Route path="auswertungen/export" element={<Auswertung />} /> {/* TODO: PDF Export */}

            {/* Aussichten (Prognosen) — Sub-Tabs route-getrieben (B1) */}
            <Route path="aussichten/:tab" element={<Aussichten />} />

            {/* Community — Sub-Tabs route-getrieben (B1) */}
            <Route path="community/:tab" element={<Community />} />

            {/* In-App-Hilfe (#130) */}
            <Route path="hilfe" element={<Hilfe />} />

            {/* Einstellungen - Stammdaten */}
            <Route path="einstellungen/anlage" element={<Anlagen />} />
            <Route path="einstellungen/strompreise" element={<Strompreise />} />
            <Route path="einstellungen/investitionen" element={<Investitionen />} />
            <Route path="einstellungen/infothek" element={<Infothek />} />
            <Route path="einstellungen/solarprognose" element={<PVGISSettings />} />

            {/* Einstellungen - Daten */}
            <Route path="einstellungen/monatsdaten" element={<Monatsdaten />} />
            <Route path="monatsabschluss/:anlageId" element={<MonatsabschlussWizard />} />
            <Route path="monatsabschluss/:anlageId/:jahr/:monat" element={<MonatsabschlussWizard />} />
            <Route path="einstellungen/energieprofil" element={<Energieprofil />} />
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

            {/* Bestands-Redirects (entfernte/umbenannte Seiten + Legacy-URLs)
                — Single Source: routes/routeManifest.ts, mitgeprüft vom
                Redirect-Auto-Test (keine Ketten, keine 404). */}
            {LEGACY_REDIRECTS.map((r) => (
              <Route key={r.from} path={r.from} element={<Navigate to={r.to} replace />} />
            ))}
          </Route>

          {/* Dev-only Vorschau-Skelett (IA-V4) — bewusst OHNE Layout, damit die
              klickbare Vorschau die eigene Top-Nav-Schale zeigt statt der alten.
              Rendert in Production null (DEV-Guard in der Komponente). */}
          <Route path="dev/design-preview" element={<DesignPreview />} />
        </Routes>
      </Suspense>
    </HashRouter>
  )
}

export default App
