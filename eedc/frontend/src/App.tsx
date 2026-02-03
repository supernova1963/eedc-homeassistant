import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/layout/Layout'
import Dashboard from './pages/Dashboard'
import Anlagen from './pages/Anlagen'
import Monatsdaten from './pages/Monatsdaten'
import Investitionen from './pages/Investitionen'
import Auswertung from './pages/Auswertung'
import Import from './pages/Import'
import Settings from './pages/Settings'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="anlagen" element={<Anlagen />} />
          <Route path="monatsdaten" element={<Monatsdaten />} />
          <Route path="investitionen" element={<Investitionen />} />
          <Route path="auswertung" element={<Auswertung />} />
          <Route path="import" element={<Import />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
