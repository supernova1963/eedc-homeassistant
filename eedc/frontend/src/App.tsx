import { HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import Dashboard from './pages/Dashboard'
import Anlagen from './pages/Anlagen'
import Monatsdaten from './pages/Monatsdaten'
import Strompreise from './pages/Strompreise'
import Investitionen from './pages/Investitionen'
import Auswertung from './pages/Auswertung'
import ROIDashboard from './pages/ROIDashboard'
import EAutoDashboard from './pages/EAutoDashboard'
import WaermepumpeDashboard from './pages/WaermepumpeDashboard'
import SpeicherDashboard from './pages/SpeicherDashboard'
import WallboxDashboard from './pages/WallboxDashboard'
import Import from './pages/Import'
import Settings from './pages/Settings'

function App() {
  // HashRouter für HA Ingress Support (Ingress-Pfad ist dynamisch)
  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="anlagen" element={<Anlagen />} />
          <Route path="monatsdaten" element={<Monatsdaten />} />
          <Route path="strompreise" element={<Strompreise />} />
          <Route path="investitionen" element={<Investitionen />} />
          <Route path="auswertung" element={<Auswertung />} />
          <Route path="roi" element={<ROIDashboard />} />
          <Route path="e-auto" element={<EAutoDashboard />} />
          <Route path="waermepumpe" element={<WaermepumpeDashboard />} />
          <Route path="speicher" element={<SpeicherDashboard />} />
          <Route path="wallbox" element={<WallboxDashboard />} />
          <Route path="import" element={<Import />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </HashRouter>
  )
}

export default App
