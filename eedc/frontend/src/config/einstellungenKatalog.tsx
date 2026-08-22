/**
 * einstellungenKatalog — datengetriebene Registry der IA-V4-Einstellungen.
 *
 * SoT für die Kategorie-Leiste + Blöcke der V4-Einstellungen-Sicht
 * ({@link ../v4/EinstellungenV4}). Jeder Eintrag ist ein Block: leichte Config
 * wird über die neue {@link FormBlock}-SoT **inline** bearbeitet (echte
 * `*Api`-Calls), schwere Wizards öffnen im {@link EinstellungenModalHost}
 * (Overlay), listen-/tabellenlastige Bereiche verweisen per Aktion auf ihre
 * bestehende Detail-Route (Deep-Link/Fallback — Routen-Inventur = Akzeptanz).
 *
 * Inhalts-SoT: `docs/drafts/archive/flip-v4/PLAN-IA-V4-RESTWEG.md` §2 (alle 17 IST-Bereiche + neue
 * Kacheln Infothek · Berichte · MQTT-Inbound · Import-Bündel). Status-Badges
 * (Schritt 3) und der Voll-Ausbau der neuen Kacheln (Schritt 4) folgen separat.
 */
import { useState, type ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Settings, Zap, Sun, BookOpen, FileText, Table2, Activity,
  ClipboardCheck, Wand2, BarChart3, Share2, Boxes,
  SlidersHorizontal, DatabaseBackup, ScrollText, Users, Plug, Wrench,
  ArrowRight, Sparkles, Trash2, Home, Network,
} from 'lucide-react'
import { FormBlock, type FormBlockFeld, type FormBlockWert } from '../components/blocks/FormBlock'
import { Alert, Button, DestructiveActionDialog } from '../components/ui'
import { useSelectedAnlage, useTheme } from '../hooks'
import { importApi, type DemoDataResult } from '../api/import'
import { StrompreiseVerwaltung } from '../pages/StrompreiseTeile'
import { AnlagenVerwaltung } from '../pages/AnlagenTeile'
import SperreEinstellung from '../components/einstellungen/SperreEinstellung'
import { MonatsdatenVerwaltung } from '../pages/MonatsdatenTeile'
import { DatenCheckerVerwaltung } from '../pages/DatenCheckerTeile'
import { EnergieprofilPflege } from '../pages/EnergieprofilTeile'
import { InfothekVerwaltung } from '../pages/InfothekTeile'
import { BackupVerwaltung } from '../pages/BackupTeile'
import { ProtokolleVerwaltung } from '../pages/ProtokolleTeile'
import { SolarprognoseVerwaltung } from '../pages/PVGISSettingsTeile'
import { MqttExportVerwaltung } from '../pages/HAExportSettingsTeile'
import MqttBrokerForm from '../components/live/MqttBrokerForm'
import HaVerbindungForm from '../components/live/HaVerbindungForm'
import VerbindungStatusBadge from '../components/live/VerbindungStatusBadge'
import DatenquellenZuordnung from '../components/live/DatenquellenZuordnung'
import { CommunityTeilenSchalter, CommunityShareBlockInhalt } from '../v4/CommunityShareBlock'
import type { WizardKey } from '../v4/EinstellungenModalHost'

// ─── Katalog-Typen ────────────────────────────────────────────────────────────

export type KategorieKey = 'stammdaten' | 'komponenten' | 'infothek' | 'daten' | 'integration' | 'datenquellen' | 'system'

export interface KategorieDef {
  key: KategorieKey
  label: string
  icon: LucideIcon
}

/** Kategorie-Leiste (2. Ebene, fix — Reihenfolge = Anzeige). Infothek = eigener Reiter
 *  (Gernot 2026-07-01). „Daten teilen" gestrichen → Community-Share als Block unter
 *  Stammdaten (Gernot 2026-07-02, A1). „Komponenten" = Geräte-Verwaltung (IST
 *  Investitionen) als eigener Reiter, direkt nach Stammdaten (Gernot 2026-07-02, P8);
 *  bewusst gleicher Name wie das Top-Menü „Komponenten" (Analyse), das hierher zur
 *  Bearbeitung verweist. Die Blöcke dieser Kategorie sind datengetrieben (ein Block
 *  pro Investitionstyp) — kein statischer Katalog-Eintrag (s. EinstellungenV4).
 *  „Datenquellen" = die feld-zentrische Zuordnungs-Fläche (Datenquellen-V4 §2g, B7),
 *  aus „Integration" herausgehoben: sie bringt eine eigene Block-Ebene pro
 *  Investitionstyp mit und lag als Katalog-Block eine Ebene zu tief (BlockShell in
 *  BlockShell). Eigener Zweig wie „Komponenten" (s. EinstellungenV4); der
 *  Katalog-Eintrag bleibt für Suche/Route/Ampel bestehen. Steht NACH „Integration",
 *  weil die Verbindungen (Broker · HA) dort die Voraussetzung der Zuordnung sind. */
export const EINSTELLUNGEN_KATEGORIEN: KategorieDef[] = [
  { key: 'stammdaten', label: 'Stammdaten', icon: Settings },
  { key: 'komponenten', label: 'Komponenten', icon: Boxes },
  { key: 'infothek', label: 'Infothek', icon: BookOpen },
  { key: 'daten', label: 'Daten', icon: Table2 },
  { key: 'integration', label: 'Integration', icon: Plug },
  { key: 'datenquellen', label: 'Datenquellen', icon: Network },
  { key: 'system', label: 'System', icon: Wrench },
]

/** Kontext, den die Shell in jede Inhalts-Render-Funktion reicht. */
export interface InhaltCtx {
  /** Öffnet einen Wizard im Modal-Host (Entsch. 2). */
  oeffneWizard: (key: WizardKey) => void
  /** Navigiert zu einer bestehenden IST-Detail-Route (`einstellungen/<seite>`). */
  navigate: (route: string) => void
  /** Öffnet den Berichte-/Dokumente-Dialog (eigenes Modal, kein Wizard). */
  oeffneBerichte: () => void
}

export type InhaltRender = (fokus: boolean, ctx: InhaltCtx) => ReactNode

export interface EinstellungEintrag {
  id: string
  name: string
  icon: LucideIcon
  kategorie: KategorieKey
  /** Primäre IST-Detail-Route (Deep-Link/Fallback). */
  route: string
  /** Weitere IST-Routen, die dieser Eintrag mit abdeckt (Bündel). */
  weitereRouten?: string[]
  /** Block-Inhalt: FormBlock (inline) · Wizard-Button · Listen-/Aktions-Übersicht. */
  inhalt: InhaltRender
  /** Optionaler interaktiver Slot in der Block-Überschrift (BlockShell-`badge`); ersetzt
   *  dort das Status-Badge. Für Aktionen, die ohne Aufklappen erreichbar sein sollen
   *  (A1: Community-„teilen"-Schalter). */
  kopfRender?: () => ReactNode
  hilfe?: string
  /** Braucht Home Assistant → sonst deaktiviert (Entsch. 6). **Zwei Stufen**, weil
   *  es zwei verschiedene Voraussetzungen sind (N-237):
   *  - `'supervisor'`: geht nur im **Add-on** (Supervisor-API — Protokolle,
   *    HA-Import, Legacy-Sensor-Zuordnung). Ohne Supervisor existiert die Route nicht.
   *  - `'verbindung'`: braucht nur eine **erreichbare** HA-Instanz, egal ob per
   *    Supervisor oder Long-Lived-Token (z. B. der Statistik-Import).
   *  Bis 2026-08-11 gab es nur `true`, und das bedeutete faktisch `'supervisor'` —
   *  wodurch Token-Nutzer auch von dem ausgesperrt waren, was ihre Verbindung kann. */
  haOnly?: 'supervisor' | 'verbindung'
  /** Freitext-Treffer für die globale Suche. */
  schlagworte?: string[]
}

// ─── Wiederverwendete Inhalts-Bausteine ───────────────────────────────────────

/** Beschreibung + optionale Aufzählung + bis zu zwei Aktionen (Modal-/Route-/Custom-Ziel). */
function StandardInhalt({
  beschreibung,
  punkte,
  aktion,
  aktionIcon: AktionIcon,
  onAktion,
  zweitAktion,
  zweitAktionIcon: ZweitAktionIcon,
  onZweitAktion,
}: {
  beschreibung: string
  punkte?: string[]
  aktion?: string
  aktionIcon?: LucideIcon
  onAktion?: () => void
  /** Optionale zweite Aktion (z. B. Backup → Wiederherstellen via Import, Entsch. 7). */
  zweitAktion?: string
  zweitAktionIcon?: LucideIcon
  onZweitAktion?: () => void
}) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-600 dark:text-gray-300">{beschreibung}</p>
      {punkte && punkte.length > 0 && (
        <ul className="space-y-1.5 text-sm text-gray-700 dark:text-gray-300">
          {punkte.map((p) => (
            <li key={p} className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-gray-300 dark:bg-gray-600" />
              {p}
            </li>
          ))}
        </ul>
      )}
      {((aktion && onAktion) || (zweitAktion && onZweitAktion)) && (
        <div className="flex flex-wrap gap-2">
          {aktion && onAktion && (
            <Button type="button" variant="secondary" size="sm" onClick={onAktion}>
              {/* D14-14 (detLAN #116): Aktions-Icons mobil weg — Text bleibt einzeilig. */}
              {AktionIcon && <AktionIcon className="max-sm:hidden h-4 w-4 mr-1.5" />}
              {aktion}
            </Button>
          )}
          {zweitAktion && onZweitAktion && (
            <Button type="button" variant="secondary" size="sm" onClick={onZweitAktion}>
              {ZweitAktionIcon && <ZweitAktionIcon className="max-sm:hidden h-4 w-4 mr-1.5" />}
              {zweitAktion}
            </Button>
          )}
        </div>
      )}
    </div>
  )
}

/** Allgemein: Darstellung/Theme inline (Client-seitig via ThemeContext). */
function AllgemeinFormInhalt({ fokus }: { fokus: boolean }) {
  const { theme, setTheme } = useTheme()
  const felder: FormBlockFeld[] = [
    {
      id: 'theme', typ: 'select', label: 'Darstellung (Theme)', wert: theme,
      optionen: [
        { value: 'system', label: 'System' },
        { value: 'light', label: 'Hell' },
        { value: 'dark', label: 'Dunkel' },
      ],
    },
  ]
  const onSave = (w: Record<string, FormBlockWert>) => {
    setTheme(w.theme as 'system' | 'light' | 'dark')
  }
  return <FormBlock felder={felder} onSave={onSave} fokus={fokus} />
}

/** Import-Assistenten-Bündel: jeder Assistent öffnet im Overlay (D17-9: auch CSV,
 *  kein navigate-Dead-End in die V3-Seite mehr). JSON-Restore ganzer Anlagen läuft
 *  über den Backup-Block, nicht hier. */
function ImportBuendelInhalt({ ctx }: { ctx: InhaltCtx }) {
  const assistenten: { key: WizardKey; label: string }[] = [
    { key: 'portal-import', label: 'Portal-Import' },
    { key: 'cloud-import', label: 'Cloud-Import (Anker, EcoFlow …)' },
    { key: 'connector', label: 'Geräte-Connector' },
    { key: 'custom-import', label: 'Eigene Datei / Vorlage' },
    { key: 'csv-import', label: 'CSV-Import' },
  ]
  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-600 dark:text-gray-300">
        Cloud- und Datei-Importe. Jeder Assistent öffnet im Overlay; die eigene Vorlage ist auch aus System/Backup erreichbar.
        JSON-Restore ganzer Anlagen läuft über den Backup-Block.
      </p>
      <div className="flex flex-wrap gap-2">
        {assistenten.map((x) => (
          <Button key={x.key} type="button" variant="secondary" size="sm" onClick={() => ctx.oeffneWizard(x.key)}>
            {x.label}
          </Button>
        ))}
      </div>
    </div>
  )
}

/** Infothek: volle native V4-Verwaltung inline im Block (alle Kategorien,
 *  Vertragspartner, N:M-Investitions-Verknüpfung, Datei-Uploads, kein navigate).
 *  Gernot 2026-07-01: die KOMPLETTE Infothek gehört IN den Block (wie Strompreise/
 *  Monatsdaten) — der große Voll-Blick läuft über Fokus/Vollbild des Blocks. */
function InfothekVollInhalt() {
  const { selectedAnlageId } = useSelectedAnlage()
  if (selectedAnlageId == null) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Anlage ausgewählt.</p>
  }
  return <InfothekVerwaltung anlageId={selectedAnlageId} />
}

/** Strompreise: native V4-Verwaltung im Block (Tabelle + Formular-Modals, kein navigate). */
function StrompreiseInhalt() {
  const { selectedAnlageId } = useSelectedAnlage()
  if (selectedAnlageId == null) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Anlage ausgewählt.</p>
  }
  return <StrompreiseVerwaltung anlageId={selectedAnlageId} />
}

/** Monatsdaten: native V4-Verwaltung inline im Block (Tabelle + alle Modals,
 *  kein navigate). Gernot 2026-07-01: die Tabelle gehört IN den Block (wie
 *  Strompreise) — der große „Voll-Blick" läuft über Fokus/Vollbild des Blocks,
 *  nicht über eine separate Seite. */
function MonatsdatenInhalt() {
  const { selectedAnlageId } = useSelectedAnlage()
  if (selectedAnlageId == null) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Anlage ausgewählt.</p>
  }
  return <MonatsdatenVerwaltung anlageId={selectedAnlageId} />
}

/** Daten-Checker: native V4-Verwaltung inline im Block (Prüf-Lauf + Kategorien +
 *  Reparatur-Werkbank, kein navigate). Wie Monatsdaten — Voll-Blick über
 *  Fokus/Vollbild des Blocks (Gernot 2026-07-01). */
function DatenCheckerInhalt() {
  const { selectedAnlageId } = useSelectedAnlage()
  if (selectedAnlageId == null) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Anlage ausgewählt.</p>
  }
  return <DatenCheckerVerwaltung anlageId={selectedAnlageId} />
}

/** Energieprofil-Pflege: nur die Pflege-Funktionen inline im Block (Datenbestand ·
 *  Backfill · Kraftstoff · Löschen · Reparatur-Werkbank), OHNE die Tages-Tabelle.
 *  Gernot 2026-07-01: Anzeige≠Pflege — die Tabelle (Anzeige) wandert zum Cockpit-
 *  Flip in die Zeit-Sicht; die Reparatur läuft über Werkbank + Daten-Checker
 *  (Zeilen-Reaggregate-Knopf damit redundant). */
function EnergieprofilPflegeInhalt() {
  const { selectedAnlage, selectedAnlageId } = useSelectedAnlage()
  if (selectedAnlageId == null) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Anlage ausgewählt.</p>
  }
  return <EnergieprofilPflege anlageId={selectedAnlageId} anlagenname={selectedAnlage?.anlagenname} />
}

/** MQTT-Export: native V4-Verwaltung inline im Block (REST-YAML · MQTT-Discovery
 *  Publish/Remove · Sensor-Übersicht · Günstig-Schwelle, kein navigate).
 *  B7-5: nicht mehr `haOnly` — Broker kommt aus dem gemeinsamen Broker-Block. */
function MqttExportInhalt() {
  const { selectedAnlage, selectedAnlageId, refresh } = useSelectedAnlage()
  if (selectedAnlageId == null) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Anlage ausgewählt.</p>
  }
  return <MqttExportVerwaltung anlageId={selectedAnlageId} anlage={selectedAnlage} onAnlageUpdated={refresh} />
}

/** Solarprognose: native V4-Verwaltung inline im Block (aktive Prognose · Horizont ·
 *  Abruf/Vorschau · optimale Ausrichtung · gespeicherte Prognosen · Wetter-Provider,
 *  kein navigate). Voll-Blick über Fokus/Vollbild des Blocks (Gernot 2026-07-01). */
function SolarprognoseInhalt() {
  const { selectedAnlage, selectedAnlageId } = useSelectedAnlage()
  if (selectedAnlageId == null) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Anlage ausgewählt.</p>
  }
  return <SolarprognoseVerwaltung anlageId={selectedAnlageId} anlage={selectedAnlage} />
}

/** Backup: voller JSON-Export + Drag-&-Drop-Restore inline im Block (kein navigate/
 *  Wizard). Gernot 2026-07-01: die Restore-Funktion ist jetzt nativ inline — der
 *  frühere Cross-Link „Aus Datei wiederherstellen → custom-import" (Entsch. 7,
 *  navigate-Stub-Zeit) entfällt damit, weil der JSON-Restore hier direkt liegt. */
function BackupInhalt() {
  const { selectedAnlage, selectedAnlageId, refresh } = useSelectedAnlage()
  if (selectedAnlageId == null) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Anlage ausgewählt.</p>
  }
  return (
    <BackupVerwaltung
      anlageId={selectedAnlageId}
      anlagenname={selectedAnlage?.anlagenname}
      onRestored={refresh}
    />
  )
}

/** F2 (2026-07-11): Demo-Daten erstellen/löschen im V4-Block (Onboarding-Parität
 *  zur V3-Import-Seite; gleiche API `importApi.createDemoData/deleteDemoData`).
 *  Löschen läuft über den M9-Kanon `DestructiveActionDialog` (Tipp-Bestätigung). */
function DemoDatenInhalt() {
  const { anlagen, refresh } = useSelectedAnlage()
  const [laeuft, setLaeuft] = useState(false)
  const [ergebnis, setErgebnis] = useState<DemoDataResult | null>(null)
  const [fehler, setFehler] = useState<string | null>(null)
  const [loeschDialog, setLoeschDialog] = useState(false)
  const demoAnlage = anlagen.find((a) => a.anlagenname === 'Demo-Anlage')

  const erstellen = async () => {
    setLaeuft(true); setFehler(null); setErgebnis(null)
    try {
      setErgebnis(await importApi.createDemoData())
      refresh()
    } catch (e) {
      setFehler(e instanceof Error ? e.message : 'Fehler beim Erstellen der Demo-Daten')
    } finally { setLaeuft(false) }
  }

  const loeschen = async () => {
    setLaeuft(true); setFehler(null); setErgebnis(null)
    try {
      await importApi.deleteDemoData()
      setLoeschDialog(false)
      refresh()
    } catch (e) {
      setFehler(e instanceof Error ? e.message : 'Fehler beim Löschen der Demo-Daten')
    } finally { setLaeuft(false) }
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-600 dark:text-gray-300">
        {demoAnlage
          ? 'Demo-Anlage ist vorhanden. Du kannst sie löschen, um sie neu zu erstellen.'
          : 'Erstelle eine komplette Demo-Anlage mit allen Investitionstypen und 31 Monaten Testdaten — zum gefahrlosen Ausprobieren.'}
      </p>
      {fehler && <Alert type="error">{fehler}</Alert>}
      {ergebnis && <Alert type="success">{ergebnis.message}</Alert>}
      {demoAnlage ? (
        <Button type="button" variant="danger" loading={laeuft} onClick={() => setLoeschDialog(true)}>
          <Trash2 className="h-4 w-4 mr-2" />
          Demo-Anlage löschen
        </Button>
      ) : (
        <Button type="button" loading={laeuft} onClick={erstellen}>
          <Sparkles className="h-4 w-4 mr-2" />
          Demo-Daten erstellen
        </Button>
      )}
      <p className="text-xs text-gray-500 dark:text-gray-400">
        <strong>Enthält:</strong> 20 kWp PV-Anlage (3 Strings), 15 kWh Speicher, E-Auto mit V2H,
        Wärmepumpe, Wallbox, Balkonkraftwerk mit Speicher, Mini-BHKW, Strompreise 2023–2025.
      </p>
      <DestructiveActionDialog
        isOpen={loeschDialog}
        onClose={() => setLoeschDialog(false)}
        onConfirm={loeschen}
        title="Demo-Anlage löschen?"
        itemLabel="die Demo-Anlage mit allen Testdaten"
        warningMessage="Alle Demo-Monatsdaten, -Komponenten und -Strompreise werden entfernt. Echte Anlagen bleiben unberührt."
        anlageId={demoAnlage?.id}
        anlageName={demoAnlage?.anlagenname ?? 'Demo-Anlage'}
      />
    </div>
  )
}

// ─── Katalog ───────────────────────────────────────────────────────────────────

export const EINSTELLUNGEN_KATALOG: EinstellungEintrag[] = [
  // ── Stammdaten ──
  {
    // A1 (Gernot 2026-07-02): oberster Block; „teilen"-Schalter in der Block-Überschrift
    // (kopfRender), Inhalt = Vorschau der anonym geteilten Daten (abgeblendet wenn aus).
    id: 'community', name: 'Community-Share', icon: Users, kategorie: 'stammdaten',
    route: 'einstellungen/community', hilfe: 'Hilfe: Community',
    schlagworte: ['community', 'benchmark', 'anonym', 'teilen', 'region', 'daten teilen'],
    kopfRender: () => <CommunityTeilenSchalter />,
    inhalt: () => <CommunityShareBlockInhalt />,
  },
  {
    id: 'anlage', name: 'Anlage', icon: Settings, kategorie: 'stammdaten',
    route: 'einstellungen/anlage', hilfe: 'Hilfe: Anlage einrichten',
    schlagworte: ['stammdaten', 'kwp', 'standort', 'ust', 'steuer', 'prognosequelle', 'name', 'geokoordinaten', 'mastr', 'wetter', 'versorger', 'zähler', 'pin', 'sperre', 'schützen', 'passwort', 'nur lesen'],
    // Gernot 2026-07-01: Tabelle aller Anlagen mit Bearbeiten-Modal (Strompreise-
    // Muster), statt inline eingebettetem Voll-Formular — auch bei einer Anlage.
    inhalt: () => (
      <div className="space-y-6">
        <AnlagenVerwaltung />
        {/* Die Einstellungs-PIN sitzt bewusst hier (Gernot 2026-08-22) und nicht unter
            „System": Wer die Anlage einrichtet, entscheidet auch, ob sie geschützt
            werden soll. Ohne gesetzte PIN ändert der Block nichts am Verhalten. */}
        <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
          <SperreEinstellung />
        </div>
      </div>
    ),
  },
  {
    id: 'strompreise', name: 'Strompreise', icon: Zap, kategorie: 'stammdaten',
    route: 'einstellungen/strompreise', hilfe: 'Hilfe: Strompreise',
    schlagworte: ['tarif', 'netzbezug', 'einspeisung', 'grundpreis', 'ct'],
    inhalt: () => <StrompreiseInhalt />,
  },
  {
    id: 'solarprognose', name: 'Solarprognose', icon: Sun, kategorie: 'stammdaten',
    route: 'einstellungen/solarprognose', hilfe: 'Hilfe: Solarprognose',
    schlagworte: ['pvgis', 'ertragsprognose', 'systemverluste', 'horizont', 'ausrichtung', 'wetter-provider'],
    // Gernot 2026-07-01: volle PVGIS-Verwaltung inline IM Block (kein navigate).
    // Voll-Blick über Fokus/Vollbild des Blocks.
    inhalt: () => <SolarprognoseInhalt />,
  },
  // ── Infothek (eigener Reiter, Gernot 2026-07-01) ──
  {
    id: 'infothek', name: 'Infothek', icon: BookOpen, kategorie: 'infothek',
    route: 'einstellungen/infothek', hilfe: 'Hilfe: Infothek',
    schlagworte: ['wissen', 'notizen', 'dokumente', 'links', 'vertragspartner', 'verträge', 'zähler'],
    inhalt: () => <InfothekVollInhalt />,
  },
  {
    id: 'berichte', name: 'Berichte & Dokumente', icon: FileText, kategorie: 'infothek',
    // Noch keine eigene IST-Route (DokumentationsDialog-Hub) → primär auf Infothek verankert.
    route: 'einstellungen/infothek', hilfe: 'Hilfe: Berichte',
    schlagworte: ['pdf', 'jahresbericht', 'dossier', 'zip', 'export'],
    inhalt: (_f, ctx) => (
      <StandardInhalt
        beschreibung="Anlagengebundene PDF-Berichte und Dossiers — einzeln oder als ZIP, mit Jahr-Auswahl."
        punkte={['Jahresbericht', 'Anlagendokumentation', 'Finanzbericht', 'Infothek-Dossier']}
        aktion="Berichte & ZIP erstellen" aktionIcon={FileText}
        onAktion={ctx.oeffneBerichte}
      />
    ),
  },

  // ── Daten ──
  {
    id: 'monatsdaten', name: 'Monatsdaten', icon: Table2, kategorie: 'daten',
    route: 'einstellungen/monatsdaten',
    schlagworte: ['zählerstände', 'monat', 'netzbezug', 'monatsabschluss'],
    // Gernot 2026-07-01: Tabelle inline IM Block (wie Strompreise), nicht hinter
    // „öffnen" auf eigener Seite. Der große Voll-Blick = Fokus/Vollbild des Blocks.
    inhalt: () => <MonatsdatenInhalt />,
  },
  {
    id: 'energieprofil', name: 'Energieprofil-Pflege', icon: Activity, kategorie: 'daten',
    route: 'einstellungen/energieprofil',
    schlagworte: ['backfill', 'reaggregieren', 'tag neu berechnen', 'ha-statistik', 'werkbank'],
    // Gernot 2026-07-01: nur die Pflege-Funktionen inline IM Block (Datenbestand ·
    // Backfill · Kraftstoff · Löschen · Reparatur-Werkbank), OHNE Tages-Tabelle
    // (Anzeige≠Pflege, wandert zum Cockpit-Flip). Kein navigate/keine separate Seite.
    inhalt: () => <EnergieprofilPflegeInhalt />,
  },
  {
    id: 'datenchecker', name: 'Daten-Checker', icon: ClipboardCheck, kategorie: 'daten',
    route: 'einstellungen/daten-checker', hilfe: 'Hilfe: Daten-Checker',
    schlagworte: ['plausibilität', 'lücken', 'ausreißer', 'reparatur', 'werkbank'],
    // Gernot 2026-07-01: Prüf-Lauf + Reparatur-Werkbank inline IM Block (wie
    // Monatsdaten), Voll-Blick über Fokus/Vollbild — kein navigate/separate Seite.
    inhalt: () => <DatenCheckerInhalt />,
  },
  {
    id: 'einrichtung', name: 'Ersteinrichtung', icon: Wand2, kategorie: 'daten',
    route: 'einstellungen/einrichtung', hilfe: 'Hilfe: Erste Schritte',
    schlagworte: ['assistent', 'setup', 'geführt', 'datenquellen'],
    inhalt: (_f, ctx) => (
      <StandardInhalt
        beschreibung="Geführte Einrichtung in einem Durchlauf: Anlage, Sensoren und Strompreise."
        punkte={['Anlage anlegen', 'Sensoren zuordnen', 'Strompreise erfassen', 'Fertig']}
        aktion="Assistent öffnen" aktionIcon={ArrowRight}
        onAktion={() => ctx.oeffneWizard('einrichtung')}
      />
    ),
  },

  // ── Integration (HA-only = im Standalone deaktiviert) ──
  // Datenquellen-V4 / B1 (§2a): Verbindungs-Block ZUERST — „Verbindung" getrennt von
  // „was darüber fließt". EIN Broker für Inbound/Gateway/Export. NICHT haOnly (der
  // MQTT-Broker ist gerade der Standalone-Pfad, unabhängig von Home Assistant).
  {
    id: 'mqtt-broker', name: 'MQTT-Broker-Verbindung', icon: Plug, kategorie: 'integration',
    route: 'einstellungen/mqtt-broker',
    schlagworte: ['mqtt', 'broker', 'verbindung', 'host', 'port', 'benutzer', 'passwort'],
    // Verbindung + Import-Richtung im Block-Kopf (auch zugeklappt sichtbar) —
    // beides wird in DIESEM Block gepflegt. Der Export hat sein eigenes Badge.
    kopfRender: () => <VerbindungStatusBadge kind="mqtt" />,
    inhalt: () => <MqttBrokerForm />,
  },
  // Datenquellen-V4 / B4a (§2a): zweiter Verbindungs-Block. NICHT haOnly — im
  // Standalone das URL/Token-Formular, in der HA-App nur Supervisor-Status. Nur
  // Basis (einrichten/testen); HA-Sensoren als Quelle nutzbar machen = P3.
  {
    id: 'ha-verbindung', name: 'HA-Verbindung', icon: Home, kategorie: 'integration',
    route: 'einstellungen/ha-verbindung',
    schlagworte: ['home assistant', 'verbindung', 'token', 'long-lived', 'url', 'remote', 'standalone'],
    // Aktiv/Inaktiv im Block-Kopf; HA-App/Supervisor = immer aktiv (auch ohne Token).
    kopfRender: () => <VerbindungStatusBadge kind="ha" />,
    inhalt: () => <HaVerbindungForm />,
  },
  // Datenquellen-V4 / §2g (B7): Export NACH den Verbindungs-Blöcken, Import zuletzt.
  {
    id: 'ha-export', name: 'MQTT-Export', icon: Share2, kategorie: 'integration',
    route: 'einstellungen/ha-export', hilfe: 'Hilfe: MQTT-Export',
    schlagworte: ['mqtt', 'broker', 'topic', 'sensoren', 'home assistant', 'discovery', 'yaml', 'rest'],
    // B7-5d: eigenes Badge — jedes Badge beschreibt nur seinen eigenen Block
    // (der Export-Toggle sitzt hier, also gehört sein Zustand auch hierher).
    kopfRender: () => <VerbindungStatusBadge kind="mqtt-export" />,
    // Gernot 2026-07-02: volle Export-Verwaltung inline IM Block (kein navigate).
    // B7-5 (§2g): NICHT mehr haOnly — der Export nutzt jetzt den gemeinsamen
    // DB-Broker (ENV nur Fallback) statt der HA-Add-on-ENV. Damit kann auch eine
    // Standalone-Instanz ihre Sensoren an einen beliebigen Broker publizieren;
    // die MQTT-Discovery dort ist HA-Konvention, aber kein HA-Zwang.
    inhalt: () => <MqttExportInhalt />,
  },
  {
    id: 'ha-statistik-import', name: 'Statistik-Import', icon: BarChart3, kategorie: 'integration',
    // N-237: 'verbindung', nicht 'supervisor' — die Langzeitstatistik liest der
    // Dienst per Recorder-DB oder WebSocket, beides auch aus einem Container heraus.
    route: 'einstellungen/ha-statistik-import', haOnly: 'verbindung',
    schlagworte: ['home assistant', 'langzeit', 'lts', 'rückwirkend', 'import'],
    inhalt: (_f, ctx) => (
      <StandardInhalt
        beschreibung="Langzeit-Statistik aus Home Assistant rückwirkend importieren."
        punkte={['Quelle wählen', 'Zeitraum festlegen', 'Vorschau prüfen', 'Importieren']}
        aktion="Import öffnen" aktionIcon={ArrowRight}
        onAktion={() => ctx.oeffneWizard('ha-statistik-import')}
      />
    ),
  },
  {
    id: 'import-buendel', name: 'Import-Assistenten', icon: Boxes, kategorie: 'integration',
    route: 'einstellungen/portal-import',
    weitereRouten: [
      'einstellungen/import', 'einstellungen/cloud-import',
      'einstellungen/custom-import', 'einstellungen/connector',
    ],
    schlagworte: ['cloud', 'anker', 'ecoflow', 'csv', 'json', 'vorlage', 'connector'],
    inhalt: (_f, ctx) => <ImportBuendelInhalt ctx={ctx} />,
  },

  // ── Datenquellen (eigene Kategorie, Datenquellen-V4 §2g/B7) ──
  // Die Fläche ist datengetrieben (ein Block je Investitionstyp) und rendert im
  // Kategorie-Zweig von EinstellungenV4 direkt — dieser Eintrag trägt nur noch
  // Suche, Route (v3ZuV4Route-Ziel) und Status-Ampel.
  {
    id: 'datenquellen', name: 'Datenquellen-Zuordnung', icon: Network, kategorie: 'datenquellen',
    route: 'einstellungen/datenquellen',
    // B7: die Routen der aufgelösten Alt-Wizards zeigen auf die Fläche — hält die
    // Routen-Abdeckung vollständig und führt V3-Deep-Links (v3ZuV4Route) hierher.
    weitereRouten: ['einstellungen/sensor-mapping', 'einstellungen/mqtt-inbound'],
    schlagworte: [
      'datenquelle', 'zuordnung', 'feld', 'sensor', 'topic', 'mqtt', 'live', 'energie',
      // B7: die aufgelösten Alt-Wizards bleiben über ihre Begriffe auffindbar.
      'sensor-zuordnung', 'mapping', 'entity', 'home assistant', 'inbound', 'gateway',
    ],
    inhalt: () => <DatenquellenZuordnung />,
  },

  // ── System ──
  {
    id: 'demo-daten', name: 'Demo-Daten', icon: Sparkles, kategorie: 'system',
    route: 'einstellungen/import',
    schlagworte: ['demo', 'testdaten', 'beispiel', 'onboarding', 'ausprobieren'],
    // F2 (Mängelbehebung 2026-07-11): V4-Zugang für Erstellen/Löschen der
    // Demo-Anlage (Onboarding-Parität zur V3-Import-Seite).
    inhalt: () => <DemoDatenInhalt />,
  },
  {
    id: 'allgemein', name: 'Allgemein', icon: SlidersHorizontal, kategorie: 'system',
    route: 'einstellungen/allgemein',
    schlagworte: ['theme', 'darstellung', 'hell', 'dunkel', 'optionen'],
    inhalt: (f) => <AllgemeinFormInhalt fokus={f} />,
  },
  {
    id: 'backup', name: 'Backup', icon: DatabaseBackup, kategorie: 'system',
    route: 'einstellungen/backup',
    schlagworte: ['sicherung', 'wiederherstellen', 'restore', 'datenbank', 'json', 'export'],
    // Gernot 2026-07-01: voller JSON-Export + Restore inline IM Block (kein
    // navigate/Wizard). Voll-Blick über Fokus/Vollbild des Blocks.
    inhalt: () => <BackupInhalt />,
  },
  {
    id: 'protokolle', name: 'Protokolle', icon: ScrollText, kategorie: 'system',
    route: 'einstellungen/protokolle',
    schlagworte: ['logs', 'system', 'fehler', 'aktivitäten', 'debug', 'neustart'],
    // Gernot 2026-07-01: System-Log-Viewer + Aktivitätsprotokoll + Debug/Neustart
    // inline IM Block (kein navigate). Voll-Blick über Fokus/Vollbild des Blocks.
    inhalt: () => <ProtokolleVerwaltung />,
  },
]

// ─── Helfer (Shell + Tests) ────────────────────────────────────────────────────

/** Einträge einer Kategorie (Reihenfolge = Katalog-Reihenfolge). */
export function eintraegeDerKategorie(kategorie: KategorieKey): EinstellungEintrag[] {
  return EINSTELLUNGEN_KATALOG.filter((e) => e.kategorie === kategorie)
}

/** Globale Fuzzy-Suche über Name · Kategorie-Label · Schlagworte (alle Tokens müssen matchen). */
export function sucheEintraege(query: string): EinstellungEintrag[] {
  const q = query.trim().toLowerCase()
  if (!q) return []
  const tokens = q.split(/\s+/)
  const labelOf = (k: KategorieKey) => EINSTELLUNGEN_KATEGORIEN.find((c) => c.key === k)?.label ?? ''
  return EINSTELLUNGEN_KATALOG.filter((e) => {
    const heu = [e.name, labelOf(e.kategorie), ...(e.schlagworte ?? [])].join(' ').toLowerCase()
    return tokens.every((t) => heu.includes(t))
  })
}

/** Welche HA-Voraussetzung fehlt diesem Eintrag? `null` = er ist nutzbar (N-237).
 *
 * Bewusst eine reine Funktion und kein Ausdruck in der Shell: sie entscheidet,
 * wer eine Fläche zu sehen bekommt, und ist damit prüfbar — vorher stand die
 * Regel als `e.haOnly && !haVerfuegbar` mitten im Rendering.
 */
export function fehlendeHAVoraussetzung(
  eintrag: Pick<EinstellungEintrag, 'haOnly'>,
  umgebung: { addon: boolean; verbunden: boolean },
): 'supervisor' | 'verbindung' | null {
  if (!eintrag.haOnly) return null
  if (eintrag.haOnly === 'supervisor') return umgebung.addon ? null : 'supervisor'
  // 'verbindung' — der Add-on-Betrieb ist immer auch verbunden, das deckt
  // `umgebung.verbunden` bereits ab (Backend: Supervisor ODER Token).
  return umgebung.verbunden ? null : 'verbindung'
}

/** Alle IST-`einstellungen/*`-Routen, die der Katalog abdeckt (Routen-Inventur). */
export function alleAbgedecktenRouten(): string[] {
  const s = new Set<string>()
  for (const e of EINSTELLUNGEN_KATALOG) {
    s.add(e.route)
    for (const r of e.weitereRouten ?? []) s.add(r)
  }
  return [...s]
}
