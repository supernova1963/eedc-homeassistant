/**
 * LayoutV4 — Schale für den IA-v4-Routenbaum (`/v4/…`), nur hinter `VITE_IA_V4`.
 *
 * Bewusst PARALLEL zur Produktiv-`components/layout/Layout`. Die obere Leiste ist
 * jetzt die geteilte {@link IATopNav} (Struktur-SoT, auch von der Vorschau
 * konsumiert) — volle 3-Achsen-Nav (Cockpit · Komponenten · Auswertungen ·
 * Community) + Meta (Hilfe · Einstellungen) + Theme-Cycle + Hamburger. Noch nicht
 * gebaute Achsen zeigen einen Platzhalter ({@link V4Platzhalter}); ihr echter
 * Bau folgt nach Phase 3. Mobile-Querschnitt: `h-dvh`, Touch-Targets ≥ 44 px.
 */
import { Outlet, useLocation } from 'react-router-dom'
import { LayoutDashboard, Boxes, BarChart3, Users, HelpCircle, Settings } from 'lucide-react'
import { IATopNav, type IANavItem } from '../components/layout/IATopNav'
import { AnlagenSelektor } from './AnlagenSelektor'

export default function LayoutV4() {
  const { pathname } = useLocation()
  const aktiv = (praefix: string) => pathname.startsWith(praefix)

  // Inhalts-Achse (Struktur-SoT: KONZEPT-IA-V4). Achsen-Aktivität via Pfad-Präfix
  // (eine Achse bleibt aktiv über all ihre Sub-Routen).
  const inhalt: IANavItem[] = [
    { key: 'cockpit',      label: 'Cockpit',      icon: LayoutDashboard, to: '/v4/cockpit/monat',        active: aktiv('/v4/cockpit') },
    { key: 'komponenten',  label: 'Komponenten',  icon: Boxes,           to: '/v4/komponenten',          active: aktiv('/v4/komponenten') },
    { key: 'auswertungen', label: 'Auswertungen', icon: BarChart3,       to: '/v4/auswertungen',         active: aktiv('/v4/auswertungen') },
    { key: 'community',    label: 'Community',    icon: Users,           to: '/v4/community',            active: aktiv('/v4/community') },
  ]
  const meta: IANavItem[] = [
    { key: 'hilfe',         label: 'Hilfe',         icon: HelpCircle, to: '/v4/hilfe',         active: aktiv('/v4/hilfe') },
    { key: 'einstellungen', label: 'Einstellungen', icon: Settings,   to: '/v4/einstellungen', active: aktiv('/v4/einstellungen') },
  ]

  const badge = (
    <span className="ml-3 px-2 py-0.5 text-[10px] font-mono rounded bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200">
      Vorschau
    </span>
  )

  return (
    <div className="h-dvh bg-gray-50 dark:bg-gray-900 flex flex-col overflow-hidden">
      <IATopNav inhalt={inhalt} meta={meta} modusBadge={badge} anlagenSelektor={<AnlagenSelektor />} />
      {/* Ab lg gibt main keine eigene Scroll-Leiste mehr her, sondern wird flex-
          Container für die ViewShell (fixe 2. Leiste). Mobile: alles scrollt. */}
      <main className="flex-1 overflow-auto lg:overflow-hidden lg:flex lg:flex-col lg:min-h-0">
        <Outlet />
      </main>
    </div>
  )
}
