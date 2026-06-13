/**
 * preview-main — Entry NUR für die öffentliche IA-v4-Vorschau (Etappe 2).
 *
 * Mountet das guard-freie `<IASkeleton/>` direkt — ohne Router, ohne
 * AppWithSetup, ohne API-Clients (das Skelett trägt nur internen State und
 * Dummy-Werte). `ThemeProvider` ist drin, damit die Vorschau die
 * System-Dark-Mode-Präferenz respektiert (viele Tester nutzen Dark-HA).
 *
 * Gebaut über `vite.preview.config.ts` (`npm run build:preview`) → `preview-dist/`.
 * Greift NICHT in den Produktiv-Entry `main.tsx` / `npm run build` ein.
 */

import React from 'react'
import ReactDOM from 'react-dom/client'
import IASkeleton from './components/preview/IASkeleton'
import './index.css'
import { ThemeProvider } from './context/ThemeContext'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ThemeProvider>
      <IASkeleton />
    </ThemeProvider>
  </React.StrictMode>,
)
