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
import { Home, type LucideIcon } from 'lucide-react'
import { STATUS_ICONS } from '../lib'
import { IASubTabBar } from '../components/layout/IASubTabBar'
import { ViewShell } from './ViewShell'
import { BlockShell, type Block } from '../components/blocks'
import { ParkProvider, ParkFuss } from '../components/park'
import { Alert, LoadingSpinner, Input } from '../components/ui'
import { useHAAvailable } from '../hooks/useHAAvailable'
import { useSelectedAnlage } from '../hooks'
import { INVESTITION_TYP_ORDER, TYP_LABELS as INVESTITION_TYP_LABELS } from '../lib/constants'
import {
  useInvestitionenVerwaltung, TYP_ICON_STYLE, TypNeuButton, TypGeraeteListe,
} from '../pages/InvestitionenTeile'
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
  ok: { icon: STATUS_ICONS.ok, farbe: 'text-green-500', titel: 'eingerichtet' },
  warn: { icon: STATUS_ICONS.warnung, farbe: 'text-amber-500', titel: 'braucht Aufmerksamkeit' },
  neu: { icon: STATUS_ICONS.info, farbe: 'text-blue-500', titel: 'neu — noch nicht eingerichtet' },
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

/**
 * Datengetriebener Zweig der Kategorie „Komponenten" (P8, Gernot 2026-07-02):
 * ein {@link BlockShell}-Block PRO Investitionstyp (`INVESTITION_TYP_ORDER`,
 * default zu), Inhalt = Geräte-Liste des Typs; „+" in der Block-Überschrift legt
 * ein neues Gerät des Typs an. Kein statischer Katalog-Eintrag — die Blöcke
 * entstehen zur Laufzeit aus `investitionenApi` (via {@link useInvestitionenVerwaltung}).
 * Bearbeiten/Neuanlage laufen über das `InvestitionForm`-Modal (kein navigate nach V3).
 * Reihenfolge NICHT sortierbar → die Typ-Reihenfolge bleibt an die Kanon-SoT gebunden
 * (konsistent zu Cockpit-Komponenten / Sensor-Zuordnung).
 */
function KomponentenEinstellungen() {
  const { selectedAnlage, selectedAnlageId } = useSelectedAnlage()
  const v = useInvestitionenVerwaltung(selectedAnlageId ?? undefined, selectedAnlage?.anlagenname)

  if (selectedAnlageId == null) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Anlage ausgewählt.</p>
  }
  if (v.loading) {
    return <LoadingSpinner text="Lade Komponenten…" />
  }

  const bloecke: Block[] = INVESTITION_TYP_ORDER.map((typ) => {
    const style = TYP_ICON_STYLE[typ]
    const anzahl = v.typCounts[typ] ?? 0
    const label = INVESTITION_TYP_LABELS[typ]
    return {
      id: `komponenten-${typ}`,
      title: label,
      icon: style.icon,
      farbe: style.color,
      summary: `${anzahl} vorhanden`,
      defaultOpen: false,
      badge: <TypNeuButton onClick={() => v.oeffneNeu(typ)} label={label} />,
      render: () => (
        <TypGeraeteListe
          geraete={v.geraeteDesTyps(typ)}
          onEdit={v.oeffneBearbeiten}
          onDelete={v.frageLoeschen}
        />
      ),
    }
  })

  return (
    <div className="space-y-3">
      {v.hinweise}
      {/* D14-2 (detLAN #113): Klapp-Zustand wird wieder gemerkt — die A3-Flüchtigkeit
          (immer alles zu beim Betreten) ist damit zurückgenommen. */}
      <BlockShell persistKey="v4-einst-komponenten" bloecke={bloecke} />
      {v.modals}
    </div>
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
  // Kategorie „Komponenten" ist datengetrieben (ein Block pro Investitionstyp) und hat
  // KEINE statischen Katalog-Einträge → eigener Zweig (nur außerhalb der Suche; die Suche
  // läuft weiter über den statischen Katalog).
  const istKomponenten = !suchModus && kategorie === 'komponenten'
  const eintraege: EinstellungEintrag[] = suchModus ? sucheEintraege(suche) : eintraegeDerKategorie(kategorie)

  const bloecke: Block[] = eintraege.map((e) => {
    const deaktiviert = e.haOnly && !haVerfuegbar
    // Kein Badge für deaktivierte HA-only-Einträge (Signal gilt dort nicht) und
    // kein Badge ohne belegtes Signal (kein erfundenes ✓).
    const st = deaktiviert ? undefined : statusMap[e.id]
    // A1: interaktiver Kopf-Slot (z. B. Community-„teilen"-Schalter) hat Vorrang vor
    // dem Status-Badge; sonst normales Status-Badge (falls belegtes Signal).
    const kopf = !deaktiviert && e.kopfRender
      ? e.kopfRender()
      : st ? <StatusBadge status={st.status} hinweis={st.hinweis} /> : undefined
    return {
      id: e.id,
      title: e.name,
      icon: e.icon,
      defaultOpen: false,
      badge: kopf,
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
          {/* B15: ui/Input-SoT (42-px-Formular-Höhe + Focus-Ring) statt rohem <input> mit 44px. */}
          <Input
            type="search"
            value={suche}
            onChange={(e) => setSuche(e.target.value)}
            placeholder="Suchen in allen Einstellungen …"
            aria-label="Einstellungen durchsuchen"
          />
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-400 dark:text-gray-500">
            <span className="flex items-center gap-1"><STATUS_META.ok.icon className={`h-3.5 w-3.5 ${STATUS_META.ok.farbe}`} /> eingerichtet</span>
            <span className="flex items-center gap-1"><STATUS_META.warn.icon className={`h-3.5 w-3.5 ${STATUS_META.warn.farbe}`} /> braucht Aufmerksamkeit</span>
            <span className="flex items-center gap-1"><STATUS_META.neu.icon className={`h-3.5 w-3.5 ${STATUS_META.neu.farbe}`} /> neu</span>
          </div>
        </div>

        <div className="p-3 sm:p-6 pt-3 max-w-[1920px] mx-auto">
          {istKomponenten ? (
            <KomponentenEinstellungen />
          ) : bloecke.length > 0 ? (
            // D14-2: Klapp-Zustand pro Kategorie gemerkt (A3-Flüchtigkeit zurückgenommen).
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
