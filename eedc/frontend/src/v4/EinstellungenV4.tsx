/**
 * EinstellungenV4 — Einstellungen-Sicht der IA-V4 (Kategorie-Leiste + Blöcke).
 *
 * Struktur = Design-SoT `components/preview/IASkeleton.tsx` (`EinstellungenView`):
 * zweite Leiste = Kategorien (Stammdaten · Daten · Integration · System · Daten
 * teilen), jede Einstellung = ein {@link BlockShell}-Block. Inhalt kommt aus dem
 * datengetriebenen {@link EINSTELLUNGEN_KATALOG}: leichte Config inline (FormBlock),
 * schwere Wizards über den {@link EinstellungenModalHost} (Overlay), Rest per
 * Aktion auf die bestehende Detail-Route.
 *
 * Status-Badges (Schritt 3) ziehen aus {@link useEinstellungenStatus} (nur
 * vorhandene Signale, kein 2. Severity-Kanon); der Voll-Ausbau der neuen Kacheln
 * (Schritt 4) folgt separat.
 */
import { lazy, Suspense, useState } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { CheckCircle2, AlertTriangle, Sparkles, Home, type LucideIcon } from 'lucide-react'
import { IASubTabBar } from '../components/layout/IASubTabBar'
import { ViewShell } from './ViewShell'
import { BlockShell, type Block } from '../components/blocks'
import { ParkProvider, ParkFuss } from '../components/park'
import { Alert } from '../components/ui'
import { useHAAvailable } from '../hooks/useHAAvailable'
import { useSelectedAnlage } from '../hooks'
import { useEinstellungenStatus, type KachelStatus } from '../hooks/useEinstellungenStatus'
import { EinstellungenModalHost, type WizardKey } from './EinstellungenModalHost'

// Berichte-/Dokumente-Hub: eigenes Modal (kein Wizard) → lazy, damit die DCE ihn
// bei Feature-Flag aus mit dem v4-Baum wegwirft.
const DokumentationsDialog = lazy(() => import('../components/DokumentationsDialog'))
import {
  EINSTELLUNGEN_KATEGORIEN, eintraegeDerKategorie, sucheEintraege,
  type EinstellungEintrag, type InhaltCtx, type KategorieKey,
} from '../config/einstellungenKatalog'

/**
 * Icon + Farbe je Badge-Status (Muster = IASkeleton `STATUS_META`, gespeist aus
 * dem echten Status-Kanon: grün/amber/blau). Farbe = Tailwind-Text-Klasse
 * (Status-Achse, kein Hex → check:design).
 */
const STATUS_META: Record<KachelStatus, { icon: LucideIcon; farbe: string; titel: string }> = {
  ok: { icon: CheckCircle2, farbe: 'text-green-500', titel: 'eingerichtet' },
  warn: { icon: AlertTriangle, farbe: 'text-amber-500', titel: 'braucht Aufmerksamkeit' },
  neu: { icon: Sparkles, farbe: 'text-blue-500', titel: 'neu — noch nicht eingerichtet' },
}

/** Status-Icon für den Block-Kopf (Tooltip = Grund, sonst Standardtitel). */
function StatusBadge({ status, hinweis }: { status: KachelStatus; hinweis?: string }) {
  const m = STATUS_META[status]
  const titel = hinweis ?? m.titel
  return (
    <span title={titel} className="flex items-center">
      <m.icon className={`h-4 w-4 ${m.farbe}`} aria-label={titel} />
    </span>
  )
}

/** Hinweis-Inhalt für HA-only-Einträge im Standalone (Entsch. 6). */
function HAOnlyHinweis() {
  return (
    <Alert type="info">
      Diese Einstellung ist nur mit aktiver Home-Assistant-Integration verfügbar.
    </Alert>
  )
}

export default function EinstellungenV4() {
  const { kategorie } = useParams<{ kategorie: string }>()
  const gueltig = EINSTELLUNGEN_KATEGORIEN.some((k) => k.key === kategorie)
  // Index / unbekannte Kategorie → Default (Stammdaten).
  if (!gueltig) return <Navigate to="/v4/einstellungen/stammdaten" replace />
  return <EinstellungenInner kategorie={kategorie as KategorieKey} />
}

function EinstellungenInner({ kategorie }: { kategorie: KategorieKey }) {
  const navigate = useNavigate()
  const haVerfuegbar = useHAAvailable()
  const { selectedAnlage } = useSelectedAnlage()
  const statusMap = useEinstellungenStatus()
  const [suche, setSuche] = useState('')
  const [offenerWizard, setOffenerWizard] = useState<WizardKey | null>(null)
  const [berichteOffen, setBerichteOffen] = useState(false)

  const ctx: InhaltCtx = {
    oeffneWizard: setOffenerWizard,
    navigate: (route) => navigate(`/${route}`),
    oeffneBerichte: () => setBerichteOffen(true),
  }

  const suchModus = suche.trim().length > 0
  const eintraege: EinstellungEintrag[] = suchModus ? sucheEintraege(suche) : eintraegeDerKategorie(kategorie)

  const bloecke: Block[] = eintraege.map((e) => {
    const deaktiviert = e.haOnly && !haVerfuegbar
    // Kein Badge für deaktivierte HA-only-Einträge (Signal gilt dort nicht) und
    // kein Badge ohne belegtes Signal (kein erfundenes ✓).
    const st = deaktiviert ? undefined : statusMap[e.id]
    return {
      id: e.id,
      title: e.name,
      icon: e.icon,
      defaultOpen: false,
      badge: st ? <StatusBadge status={st.status} hinweis={st.hinweis} /> : undefined,
      render: (fokus: boolean) => (deaktiviert ? <HAOnlyHinweis /> : e.inhalt(fokus, ctx)),
    }
  })

  const nav = (
    <IASubTabBar
      items={EINSTELLUNGEN_KATEGORIEN.map((k) => ({
        key: k.key, label: k.label, to: `/v4/einstellungen/${k.key}`,
      }))}
    />
  )

  return (
    <ParkProvider persistKey="v4-einstellungen">
      <ViewShell bar={nav}>
        <div className="px-3 sm:px-6 pt-4 space-y-3 max-w-[1920px] mx-auto">
          <input
            type="search"
            value={suche}
            onChange={(e) => setSuche(e.target.value)}
            placeholder="Suchen in allen Einstellungen …"
            aria-label="Einstellungen durchsuchen"
            className="w-full min-h-[44px] rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-4 text-sm text-gray-900 dark:text-white"
          />
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-400 dark:text-gray-500">
            <span className="flex items-center gap-1"><CheckCircle2 className="h-3.5 w-3.5 text-green-500" /> eingerichtet</span>
            <span className="flex items-center gap-1"><AlertTriangle className="h-3.5 w-3.5 text-amber-500" /> braucht Aufmerksamkeit</span>
            <span className="flex items-center gap-1"><Sparkles className="h-3.5 w-3.5 text-blue-500" /> neu</span>
          </div>
        </div>

        <div className="p-3 sm:p-6 pt-3 max-w-[1920px] mx-auto">
          {bloecke.length > 0 ? (
            <BlockShell
              key={suchModus ? 'suche' : kategorie}
              persistKey={suchModus ? 'v4-einst-suche' : `v4-einst-${kategorie}`}
              bloecke={bloecke}
              sortierbar={!suchModus}
            />
          ) : (
            <p className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
              <Home className="h-4 w-4" /> Keine Einstellung gefunden.
            </p>
          )}
          <ParkFuss />
        </div>
      </ViewShell>

      <EinstellungenModalHost offen={offenerWizard} onClose={() => setOffenerWizard(null)} />

      {berichteOffen && (
        <Suspense fallback={null}>
          <DokumentationsDialog anlage={selectedAnlage ?? null} onClose={() => setBerichteOffen(false)} />
        </Suspense>
      )}
    </ParkProvider>
  )
}
