import { lazy, Suspense } from 'react'
import { HashRouter, Routes, Route, Navigate, useParams } from 'react-router-dom'
import { AppErrorBoundary } from './components/AppErrorBoundary'
import LoadingSpinner from './components/ui/LoadingSpinner'
import { LEGACY_REDIRECTS } from './routes/routeManifest'
import { useTouchTitleTooltip } from './hooks/useTouchTitleTooltip'

// IA-V4 ist die kanonische Oberfläche (Flip v4.0.0). Die Achsen-Dispatcher +
// LayoutV4-Schale bilden den `/`-Routenbaum; die frühere V3-Welt und der
// `/v4`-Vorschau-Präfix sind entfallen (Redirect-Mechanik „Option B").
const LayoutV4 = lazy(() => import('./v4/LayoutV4'))
const CockpitV4 = lazy(() => import('./v4/CockpitV4'))
const KomponentenV4 = lazy(() => import('./v4/KomponentenV4'))
const AuswertungenV4 = lazy(() => import('./v4/AuswertungenV4'))
const CommunityV4 = lazy(() => import('./v4/CommunityV4'))
const EinstellungenV4 = lazy(() => import('./v4/EinstellungenV4'))
const HilfeV4 = lazy(() => import('./v4/HilfeV4'))

/**
 * Stray-Bookmark-Versicherung: Vor-Flip-Vorschau-Links (`#/v4/…`) auf die
 * prefix-freien kanonischen Pfade umbiegen (`#/v4/cockpit/live` → `/cockpit/live`).
 */
function V4LegacyRedirect() {
  const params = useParams()
  const rest = params['*'] ?? ''
  return <Navigate to={`/${rest}`} replace />
}

function App() {
  useTouchTitleTooltip()
  // HashRouter für HA Ingress Support (Ingress-Pfad ist dynamisch)
  return (
    <HashRouter>
      {/* R18-1 (rapahl #207): ErrorBoundary um den GANZEN Routenbaum —
          ChunkLoadError nach Deploy / Render-Fehler enden in einem Reload-Angebot
          statt im dauerhaft schwarzen Bildschirm. */}
      <AppErrorBoundary>
        {/* R18-1: Fallback nicht `null` — beim Erst-Load über langsame Wege
            (Ingress, Companion-App übers Internet) laden LayoutV4→Cockpit→Live als
            Lazy-Chunks nacheinander; bis dahin rendert React sonst NICHTS (dunkler
            Body = „schwarzer Bildschirm"). h-dvh, nicht h-screen (iOS Safari,
            [[feedback_ios_companion_app]]). */}
        <Suspense
          fallback={
            <div className="min-h-dvh flex items-center justify-center">
              <LoadingSpinner size="lg" text="eedc lädt…" />
            </div>
          }
        >
        <Routes>
          <Route path="/" element={<LayoutV4 />}>
            {/* Landing → Live-Cockpit. */}
            <Route index element={<Navigate to="/cockpit/live" replace />} />

            {/* Cockpit (Zeit-Achse): Index → Live; `:zeit` rendert den Dispatcher. */}
            <Route path="cockpit" element={<Navigate to="/cockpit/live" replace />} />
            <Route path="cockpit/:zeit" element={<CockpitV4 />} />

            {/* Komponenten-Hub (Was-Achse): Index → erster verfügbarer Typ. */}
            <Route path="komponenten" element={<KomponentenV4 />} />
            <Route path="komponenten/:typ" element={<KomponentenV4 />} />

            {/* Auswertungen (Wie-Achse): Index → Finanzen (Default). */}
            <Route path="auswertungen" element={<Navigate to="/auswertungen/finanzen" replace />} />
            <Route path="auswertungen/:sub" element={<AuswertungenV4 />} />

            {/* Community: Index → Übersicht. */}
            <Route path="community" element={<Navigate to="/community/uebersicht" replace />} />
            <Route path="community/:sub" element={<CommunityV4 />} />

            {/* In-App-Hilfe (#130). */}
            <Route path="hilfe" element={<HilfeV4 />} />

            {/* Einstellungen (Meta-Achse): Index → Stammdaten (Default). */}
            <Route path="einstellungen" element={<Navigate to="/einstellungen/stammdaten" replace />} />
            <Route path="einstellungen/:kategorie" element={<EinstellungenV4 />} />

            {/* Bestands-Redirects (entfernte/umbenannte Seiten + Legacy-URLs)
                — Single Source: routes/routeManifest.ts, mitgeprüft vom
                Redirect-Auto-Test (keine Ketten, keine 404). */}
            {LEGACY_REDIRECTS.map((r) => (
              <Route key={r.from} path={r.from} element={<Navigate to={r.to} replace />} />
            ))}

            {/* Splat-Fänger für gelöschte dynamische Alt-Sektionen (V3-Donors). */}
            <Route path="aussichten/*" element={<Navigate to="/cockpit/aussicht" replace />} />
            <Route path="monatsabschluss/*" element={<Navigate to="/einstellungen/daten" replace />} />
          </Route>

          {/* Stray-Bookmarks aus der `/v4`-Vorschauzeit → prefix-frei umbiegen. */}
          <Route path="v4/*" element={<V4LegacyRedirect />} />
        </Routes>
        </Suspense>
      </AppErrorBoundary>
    </HashRouter>
  )
}

export default App
