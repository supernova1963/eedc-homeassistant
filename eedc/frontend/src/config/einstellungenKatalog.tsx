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
 * Inhalts-SoT: `docs/drafts/PLAN-IA-V4-…` §2 (alle 17 IST-Bereiche + neue
 * Kacheln Infothek · Berichte · MQTT-Inbound · Import-Bündel). Status-Badges
 * (Schritt 3) und der Voll-Ausbau der neuen Kacheln (Schritt 4) folgen separat.
 */
import { useEffect, useState, type ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Settings, Zap, Sun, BookOpen, FileText, Table2, Activity,
  ClipboardCheck, Wand2, MapPin, BarChart3, Share2, Boxes, Radio,
  SlidersHorizontal, DatabaseBackup, ScrollText, Users, Plug, Wrench,
  ArrowRight,
} from 'lucide-react'
import { FormBlock, type FormBlockFeld, type FormBlockWert } from '../components/blocks/FormBlock'
import { Button } from '../components/ui'
import { useSelectedAnlage, useTheme } from '../hooks'
import { liveDashboardApi, type MqttInboundStatus } from '../api/liveDashboard'
import { StrompreiseVerwaltung } from '../pages/StrompreiseTeile'
import { AnlagenVerwaltung } from '../pages/AnlagenTeile'
import { MonatsdatenVerwaltung } from '../pages/MonatsdatenTeile'
import { DatenCheckerVerwaltung } from '../pages/DatenCheckerTeile'
import { EnergieprofilPflege } from '../pages/EnergieprofilTeile'
import { InfothekVerwaltung } from '../pages/InfothekTeile'
import { BackupVerwaltung } from '../pages/BackupTeile'
import { ProtokolleVerwaltung } from '../pages/ProtokolleTeile'
import { SolarprognoseVerwaltung } from '../pages/PVGISSettingsTeile'
import { MqttExportVerwaltung } from '../pages/HAExportSettingsTeile'
import { CommunityTeilenSchalter, CommunityShareBlockInhalt } from '../v4/CommunityShareBlock'
import type { WizardKey } from '../v4/EinstellungenModalHost'

// ─── Katalog-Typen ────────────────────────────────────────────────────────────

export type KategorieKey = 'stammdaten' | 'komponenten' | 'infothek' | 'daten' | 'integration' | 'system'

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
 *  pro Investitionstyp) — kein statischer Katalog-Eintrag (s. EinstellungenV4). */
export const EINSTELLUNGEN_KATEGORIEN: KategorieDef[] = [
  { key: 'stammdaten', label: 'Stammdaten', icon: Settings },
  { key: 'komponenten', label: 'Komponenten', icon: Boxes },
  { key: 'infothek', label: 'Infothek', icon: BookOpen },
  { key: 'daten', label: 'Daten', icon: Table2 },
  { key: 'integration', label: 'Integration', icon: Plug },
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
  /** Nur mit HA-Integration nutzbar → im Standalone deaktiviert (Entsch. 6). */
  haOnly?: boolean
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

/** Import-Assistenten-Bündel: jeder Assistent öffnet im Overlay (CSV/JSON per Route). */
function ImportBuendelInhalt({ ctx }: { ctx: InhaltCtx }) {
  const assistenten: { key: WizardKey; label: string }[] = [
    { key: 'portal-import', label: 'Portal-Import' },
    { key: 'cloud-import', label: 'Cloud-Import (Anker, EcoFlow …)' },
    { key: 'connector', label: 'Geräte-Connector' },
    { key: 'custom-import', label: 'Eigene Datei / Vorlage' },
  ]
  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-600 dark:text-gray-300">
        Cloud- und Datei-Importe. Jeder Assistent öffnet im Overlay; die eigene Vorlage ist auch aus System/Backup erreichbar.
      </p>
      <div className="flex flex-wrap gap-2">
        {assistenten.map((x) => (
          <Button key={x.key} type="button" variant="secondary" size="sm" onClick={() => ctx.oeffneWizard(x.key)}>
            {x.label}
          </Button>
        ))}
        <Button type="button" variant="secondary" size="sm" onClick={() => ctx.navigate('einstellungen/import')}>
          CSV / JSON
        </Button>
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
 *  Publish/Remove · Sensor-Übersicht · Günstig-Schwelle, kein navigate). `haOnly` →
 *  der Eintrag ist im Standalone deaktiviert, dieser Inhalt rendert nur mit HA. */
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

/** MQTT-Inbound: Status + Cache-Zähler (1× gelesen), Einrichten öffnet im Modal. */
function MqttInboundInhalt({ ctx }: { ctx: InhaltCtx }) {
  const [status, setStatus] = useState<MqttInboundStatus | null>(null)
  const [anzahlWerte, setAnzahlWerte] = useState<number | null>(null)
  useEffect(() => {
    let aktiv = true
    liveDashboardApi.getMqttStatus().then((s) => { if (aktiv) setStatus(s) }).catch(() => {})
    liveDashboardApi.getMqttValues().then((v) => { if (aktiv) setAnzahlWerte(v.werte.length) }).catch(() => {})
    return () => { aktiv = false }
  }, [])
  const statusText = !status
    ? 'wird geladen …'
    : status.subscriber_aktiv
      ? `verbunden${status.broker ? ` · ${status.broker}` : ''}`
      : status.verfuegbar
        ? (status.grund ?? 'verfügbar, kein aktiver Subscriber')
        : (status.grund ?? 'nicht konfiguriert')
  const punkte = [
    `Status: ${statusText}`,
    anzahlWerte !== null ? `Empfangene Werte im Cache: ${anzahlWerte}` : 'Empfangene Werte: —',
  ]
  return (
    <StandardInhalt
      beschreibung="Live-Werte per MQTT empfangen und eedc-Feldern zuordnen."
      punkte={punkte}
      aktion="Einrichten öffnen" aktionIcon={ArrowRight}
      onAktion={() => ctx.oeffneWizard('mqtt-inbound')}
    />
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
    schlagworte: ['stammdaten', 'kwp', 'standort', 'ust', 'steuer', 'prognosequelle', 'name', 'geokoordinaten', 'mastr', 'wetter', 'versorger', 'zähler'],
    // Gernot 2026-07-01: Tabelle aller Anlagen mit Bearbeiten-Modal (Strompreise-
    // Muster), statt inline eingebettetem Voll-Formular — auch bei einer Anlage.
    inhalt: () => <AnlagenVerwaltung />,
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
  {
    id: 'sensor-mapping', name: 'Sensor-Zuordnung', icon: MapPin, kategorie: 'integration',
    route: 'einstellungen/sensor-mapping', hilfe: 'Hilfe: Sensor-Zuordnung', haOnly: true,
    schlagworte: ['home assistant', 'entity', 'feld', 'mapping'],
    inhalt: (_f, ctx) => (
      <StandardInhalt
        beschreibung="Home-Assistant-Entities den eedc-Feldern zuordnen."
        aktion="Assistent öffnen" aktionIcon={ArrowRight}
        onAktion={() => ctx.oeffneWizard('sensor-mapping')}
      />
    ),
  },
  {
    id: 'ha-statistik-import', name: 'Statistik-Import', icon: BarChart3, kategorie: 'integration',
    route: 'einstellungen/ha-statistik-import', haOnly: true,
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
    id: 'ha-export', name: 'MQTT-Export', icon: Share2, kategorie: 'integration',
    route: 'einstellungen/ha-export', hilfe: 'Hilfe: MQTT-Export', haOnly: true,
    schlagworte: ['mqtt', 'broker', 'topic', 'sensoren', 'home assistant', 'discovery', 'yaml', 'rest'],
    // Gernot 2026-07-02: volle Export-Verwaltung inline IM Block (kein navigate).
    // haOnly → im Standalone deaktiviert, rendert nur mit HA-Integration.
    inhalt: () => <MqttExportInhalt />,
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
  {
    id: 'mqtt-inbound', name: 'MQTT-Inbound', icon: Radio, kategorie: 'integration',
    route: 'einstellungen/mqtt-inbound',
    schlagworte: ['mqtt', 'empfangen', 'inbound', 'live'],
    inhalt: (_f, ctx) => <MqttInboundInhalt ctx={ctx} />,
  },

  // ── System ──
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

/** Alle IST-`einstellungen/*`-Routen, die der Katalog abdeckt (Routen-Inventur). */
export function alleAbgedecktenRouten(): string[] {
  const s = new Set<string>()
  for (const e of EINSTELLUNGEN_KATALOG) {
    s.add(e.route)
    for (const r of e.weitereRouten ?? []) s.add(r)
  }
  return [...s]
}
