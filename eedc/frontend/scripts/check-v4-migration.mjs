#!/usr/bin/env node
/**
 * check-v4-migration.mjs — Migrations-Freeze-Gate für die V4-Mängelbehebung
 * (PLAN-V4-MAENGELBEHEBUNG.md Paket W, 2026-07-11).
 *
 * Schließt die drei Scope-Löcher der bestehenden Wächter
 * ([[feedback_v4_migration_status_control_ebene]]):
 *   `check:form-controls` = nur `components/forms|setup-wizard/**` (und ohne <button>) ·
 *   `check:buttons` = nur `src/v4/**` (und nur <button>) ·
 *   `check:v4links` = nur Hash-Links (übersieht `navigate()`-Aufrufe).
 *
 * Drei Teile, alle als FREEZE (Ist-Bestand exakt eingefroren; jede Abweichung —
 * neu ODER Abbau — muss die Liste hier anfassen → die schrumpfende Liste IST die
 * Rest-Arbeitsliste der Pakete C/D/E/B):
 *
 * 1. REGISTRY-FREEZE: jeder `EinstellungenModalHost`-Registry-Eintrag
 *    (`Comp: lazy(import('../pages/X'))`) muss als MIGRIERT (Klasse A) oder
 *    REST (Klasse D / Rest-Nachzug) klassifiziert sein. Neue unklassifizierte
 *    Wizards blocken.
 *
 * 2. NAVIGATE→V3-SWEEP: `navigate('/…')` mit absolutem Nicht-`/v4`-Ziel über
 *    `src/v4/**` + die im Katalog inline gerenderten `pages/*Teile.tsx` — fängt
 *    `StatusFusszeile` + `MonatsdatenTeile` (Donor-Kanten, Paket E), die
 *    `check:v4links` als Nicht-Hash-Link übersieht. Dynamische Aufrufe wie
 *    `navigate(v3RouteZuV4(link) || link)` (DatenCheckerTeile, v4-remapped)
 *    matcht das Muster bewusst nicht.
 *
 * 3. ROH-CONTROL-SWEEP: robustes Muster `<(button|select|input|textarea)(?![A-Za-z])`
 *    (NICHT `[ >/]` — das verfehlt `<button⏎`), `type="file"` ausgenommen (keine
 *    SoT-Datei-Komponente), Kommentare gestrippt. Scope: V4-erreichbare
 *    `pages/*` (Katalog-Teile + Wizard-Registry) + `DokumentationsDialog` +
 *    `src/v4/**` + die transitiv eingebetteten Composites (Inventur §H:
 *    `components/{werte,prognose,repair,infothek,live,sensor-mapping,
 *    monatsabschluss,forms}/**`) + die sechs Infra-Dateien (§H-Infra).
 *
 * Bewusst NICHT im Scope (offene Verortung, PLAN §L):
 *   §L5 `components/energieprofil/EnergieprofilTageTabelle` (Verortung klären) ·
 *   §L6 `components/setup-wizard/**` (V4-Erreichbarkeit bestätigen; roh-seitig
 *   deckt `check:form-controls` select/input/textarea/label dort schon ab).
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')

// ---------------------------------------------------------------------------
// Teil 1 — Registry-Freeze (EinstellungenModalHost)
// ---------------------------------------------------------------------------

/** Klasse A: nachweislich Teil-D-migriert (Inventur 2026-07-09; D0 abgebaut 2026-07-11). */
const REGISTRY_MIGRIERT = new Set([
  'CloudImportWizard', 'ConnectorSetupWizard', 'CsvImportWizard',
  'DataImportWizard', 'CustomImportWizard', // D0: Rest-Roh → Button-SoT (2026-07-11)
  'HAStatistikImport', // D3 (2026-07-11): host+Blocker, SoT-Controls, Fuß-Nav Overlay-fähig
  // MonatsabschlussWizard: Monatsabschluss-V4 Bündel 6 (2026-07-12) — als V4-Fläche
  // stillgelegt, Registry-Eintrag entfernt. V4 nutzt die assistierte MonatsdatenForm.
  // Die V3-Route/-Komponente bleibt bis zum Flip (nicht mehr Teil dieser Registry).
  // MqttInboundSetup + SensorMappingWizard: Datenquellen-V4 B7 (2026-07-16) — dito als
  // V4-Flächen stillgelegt (Registry-Einträge entfernt), V4 nutzt die feld-zentrische
  // Datenquellen-Fläche (§2g). V3-Routen/-Komponenten bleiben bis zum Flip; dass kein
  // V4-Code sie wieder öffnet, sichert `check:datenquellen-aufloesung`.
  // Session 4 (2026-07-11): strukturell migriert; ihr EINZIGER Roh-Rest ist ein
  // Fall-3-Mikro-Control (Einrichtung → Karten-Kachel), von Gernot freigegeben
  // (→ ROH_INFRA). Damit MIGRIERT.
  'Einrichtung', // D1
])
/** Rest: leer — alle Registry-Wizards sind migriert (Session 4, 2026-07-11). */
const REGISTRY_REST = new Set([])

// ---------------------------------------------------------------------------
// Teil 2 — navigate→V3-Freeze (Datei → exakte Treffer-Zahl)
// ---------------------------------------------------------------------------

const NAVIGATE_ALLOW = new Map([
  // E1 GELÖST (2026-07-11): Monatsabschluss/CSV öffnen unter LayoutV4 im Overlay
  // (useOeffneWizard + Payload). Die 3 verbleibenden Literale in MonatsdatenTeile
  // sind der reine V3-FALLBACK (ohne Provider) — kein V4-Dead-End mehr.
  ['src/pages/MonatsdatenTeile.tsx', 3],
  // StatusFusszeile: 0 — E1-Kante komplett auf oeffneWizard('monatsabschluss').
  // InhaltCtx-Adapter `(route) => navigate(`/${route}`)` — dynamisches Ziel aus dem
  // Katalog; Auflösung fällt mit den C-/E-Paketen (Ziele werden Overlay/V4-Routen).
  ['src/v4/EinstellungenV4.tsx', 1],
  // einstellungenKatalog.tsx: 0 — die RESTWEG-§2b''-Donor-Kante `ctx.navigate('einstellungen/
  // import')` ist seit D17-9 (`oeffneWizard('csv-import')`) gelöst; Datei bleibt im Sweep-Scope.
])

// ---------------------------------------------------------------------------
// Teil 3 — Roh-Control-Freeze
// ---------------------------------------------------------------------------

/**
 * REST-Bestand = Migrationsschuld der Pakete C/D/E/B (Inventur-Klassen B–E + §H).
 * Session 4 (2026-07-11): **leer**. Der Bau-Teil der Mängelbehebung ist durch
 * (Paket C: Session 2 · B/D0–D4/E/F2: Session 3). Die 25 zuletzt verbliebenen
 * Roh-Controls waren Fall-3-Mikro-Optiken/Impl-Interna und sind von Gernot
 * freigegeben (→ ROH_INFRA, Gruppe „V4-Mikro-Optiken"). Ziel erreicht = leere Map.
 */
const ROH_REST = new Map([])

/**
 * INFRA-Allowlist (Inventur §H-Infra, Regel 0a Fall 3): rohe Controls SIND hier
 * die SoT-/Infra-Implementierung — keine Migration, bewusste Freigabe.
 * ✅ Von Gernot FREIGEGEBEN (2026-07-11, mit Menü-Zuordnung vorgelegt).
 */
const ROH_INFRA = new Map([
  ['src/components/ui/DatumPicker.tsx', 9], // SoT-Impl (Kalender-Grid-Buttons)
  ['src/components/ui/InlineAktion.tsx', 1], // SoT-Impl (schlanker Inline-Aktion-/Disclosure-Baustein; ersetzt rohe <button> in den V4-Erfassungs-Formularen, Monatsabschluss-V4)
  // Fall-3-Gruppe „Implementierungs-Interna" (Gernot-Freigabe 2026-07-11, C3/C9):
  ['src/components/DokumentationsDialog.tsx', 1], // Download-Karten-Kachel als <button>
  ['src/pages/InfothekTeile.tsx', 1], // Datei-Thumbnail-Kachel (56×56, → Lightbox)
  ['src/components/infothek/DateiLightbox.tsx', 3], // Overlay-Mechanik X/‹/›
  ['src/components/infothek/DateiUpload.tsx', 1], // Thumbnail-Lösch-Overlay-Badge
  ['src/components/infothek/MarkdownNotizen.tsx', 3], // Editor-Toolbar + rahmenlose textarea
  ['src/components/ui/SortableSection.tsx', 3], // SoT-Impl (Drag/Sort-Controls)
  ['src/components/blocks/BlockShell.tsx', 8], // Park/Fokus/Aufklapp-Mechanik
  ['src/components/park/GeparktBlock.tsx', 4], // Park-Mechanik
  ['src/components/layout/IATopNav.tsx', 4], // V4-Navigation
  ['src/components/preview/IASkeleton.tsx', 11], // Dev-Preview (nicht user-erreichbar)
  // ── Fall-3-Freigabe „V4-Mikro-Optiken" (Gernot 2026-07-11, Session 4; Vorlage
  //    control-level vorgelegt) ──────────────────────────────────────────────
  // Gruppe A — src/v4-Eigenoptik, deckungsgleich mit check:buttons-ALLOW (S4/S11/B3):
  ['src/v4/ZeitStepper.tsx', 3], // mobiler Zeit-Stepper (Player ‹/› · Titel-Aufklapper · Dropdown) — /#/v4/cockpit/{tag,monat,jahr}
  ['src/v4/status/StatusFusszeile.tsx', 3], // Status-Fußzeilen-Chips (global, 24-px) — alle /#/v4/*
  ['src/v4/WerkbankZeitraum.tsx', 2], // Zeitraum-/Vergleich-Schnellwahl-Chips (Einzel-Rahmen) — /#/v4/auswertungen/tabelle
  ['src/v4/TagesRail.tsx', 1], // Desktop-Tages-Rail-Eintrag — /#/v4/cockpit/tag
  ['src/v4/MonatsRail.tsx', 1], // Desktop-Monats-Rail-Eintrag — /#/v4/cockpit/monat
  ['src/v4/JahresRail.tsx', 1], // Desktop-Jahres-Rail-Eintrag — /#/v4/cockpit/jahr
  ['src/v4/TagesverlaufChart.tsx', 1], // Solo-Toggle „Autarkie %" (Verlauf) — /#/v4/cockpit/monat
  ['src/v4/JahrVerlaufChart.tsx', 1], // Solo-Toggle „Autarkie %" (Verlauf) — /#/v4/cockpit/jahr
  ['src/v4/KomponentenTypV4.tsx', 1], // Geräte-Selektor-Pill (B3, ≥2 Geräte) — /#/v4/komponenten/<typ>
  ['src/v4/CockpitLiveV4.tsx', 1], // ⤢ Fokus-Button im Energiefluss-Kartenkopf (FokusKachel-IST, S11) — /#/v4/cockpit/live
  // Gruppe B — geteilte/Composite-Mikro-Controls (gleiche Gattung; teils V3+V4):
  ['src/components/live/EnergieFluss.tsx', 2], // Live-Kartenkopf-Pillen (Hintergrund-<select> + Lite-Toggle, analog S11) — /#/v4/cockpit/live + V3 /#/live
  ['src/components/werte/WerteTabelle.tsx', 2], // Spalten-Picker Reorder-Pfeile ↑/↓ (SortableSection-Gattung) — /#/v4/auswertungen/tabelle
  ['src/components/prognose/PrognoseVergleichTeile.tsx', 1], // ⚠-Popover-Trigger in Zelle (Inline-Mikro-Trigger) — /#/v4/auswertungen/prognose + V3 /#/aussichten/prognosen
  ['src/components/sensor-mapping/FeldMappingInput.tsx', 4], // SensorAutocomplete-Combobox (Such-Input/Optionen/Clear-X/Strategie-Radio; Gattung DatumPicker-Impl) — Sensor-Zuordnung (haOnly)
  ['src/pages/Einrichtung.tsx', 1], // Datenquellen-Karten-Kachel (Kachel-Gattung wie DokumentationsDialog) — /#/v4/einstellungen/daten + V3 /#/einstellungen/einrichtung
])

// ---------------------------------------------------------------------------
// Scope-Definition
// ---------------------------------------------------------------------------

/** Im Katalog INLINE gerenderte Teile (einstellungenKatalog.tsx-Imports). */
const KATALOG_TEILE = [
  'StrompreiseTeile', 'AnlagenTeile', 'MonatsdatenTeile', 'DatenCheckerTeile',
  'EnergieprofilTeile', 'InfothekTeile', 'BackupTeile', 'ProtokolleTeile',
  'PVGISSettingsTeile', 'HAExportSettingsTeile',
]
/** Über die Wizard-Registry erreichbare pages/ (Teil 1 hält diese Liste synchron). */
const REGISTRY_PAGES = [...REGISTRY_MIGRIERT, ...REGISTRY_REST]
/** Transitive Composite-Verzeichnisse (Inventur §H). */
const COMPOSITE_DIRS = ['werte', 'prognose', 'repair', 'infothek', 'live', 'sensor-mapping', 'monatsabschluss', 'forms']

function tsxFiles(dir) {
  const out = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) out.push(...tsxFiles(p))
    else if (name.endsWith('.tsx') && !name.endsWith('.test.tsx')) out.push(p)
  }
  return out
}

const rel = (f) => relative(ROOT, f).replaceAll('\\', '/')
/** Block- und Ganz-Zeilen-Kommentare strippen (verhindert Scheintreffer wie `statt rohem <input>`). */
const stripComments = (src) => src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')

let fehler = 0
const meld = (msg) => { fehler++; console.error('✗ ' + msg) }

// --- Teil 1: Registry-Freeze ---
const hostSrc = stripComments(readFileSync(join(ROOT, 'src', 'v4', 'EinstellungenModalHost.tsx'), 'utf8'))
const registryEintraege = [...hostSrc.matchAll(/import\(['"]\.\.\/pages\/([A-Za-z0-9]+)['"]\)/g)].map((m) => m[1])
for (const name of registryEintraege) {
  if (!REGISTRY_MIGRIERT.has(name) && !REGISTRY_REST.has(name)) {
    meld(`Registry: pages/${name} ist im EinstellungenModalHost, aber weder als MIGRIERT noch als REST klassifiziert — neuen Wizard erst Teil-D-konform bauen (oder bewusst als REST eintragen).`)
  }
}
for (const name of [...REGISTRY_MIGRIERT, ...REGISTRY_REST]) {
  if (!registryEintraege.includes(name)) {
    meld(`Registry: pages/${name} steht in der Klassifikation, aber nicht (mehr) in der Registry — Eintrag hier entfernen.`)
  }
}

// --- Teil 2: navigate→V3 ---
// Fängt `navigate('/…')` (absolut, nicht /v4) UND `ctx.navigate('…')` (Katalog-Adapter,
// der Ziele über EinstellungenV4 zu `/${route}` macht — RESTWEG §2b'').
const NAV = /(?:navigate\(\s*['"`]\/(?!v4)|ctx\.navigate\(\s*['"`](?!v4))/g
const navScope = [
  ...tsxFiles(join(ROOT, 'src', 'v4')),
  ...KATALOG_TEILE.map((n) => join(ROOT, 'src', 'pages', n + '.tsx')),
  join(ROOT, 'src', 'config', 'einstellungenKatalog.tsx'),
]
const navGesehen = new Map()
for (const f of navScope) {
  const src = stripComments(readFileSync(f, 'utf8'))
  const n = (src.match(NAV) ?? []).length
  if (n > 0) navGesehen.set(rel(f), n)
}
for (const [file, n] of navGesehen) {
  const erlaubt = NAVIGATE_ALLOW.get(file) ?? 0
  if (n !== erlaubt) meld(`navigate→V3: ${file} hat ${n}× (erlaubt: ${erlaubt}) — Overlay-Host (oeffneWizard) oder V4-Route nutzen; bewusster Bestand → Freeze anpassen.`)
}
for (const [file, erlaubt] of NAVIGATE_ALLOW) {
  if (!navGesehen.has(file) && erlaubt > 0) meld(`navigate→V3: Freeze-Eintrag ohne Treffer: ${file} (erlaubt ${erlaubt}) — Eintrag entfernen (Abbau sichtbar machen).`)
}

// --- Teil 3: Roh-Control-Sweep ---
const ROH = /<(button|select|input|textarea)(?![A-Za-z])/g
const rohScope = [
  ...KATALOG_TEILE.map((n) => join(ROOT, 'src', 'pages', n + '.tsx')),
  ...REGISTRY_PAGES.map((n) => join(ROOT, 'src', 'pages', n + '.tsx')),
  join(ROOT, 'src', 'components', 'DokumentationsDialog.tsx'),
  ...tsxFiles(join(ROOT, 'src', 'v4')),
  ...COMPOSITE_DIRS.flatMap((d) => tsxFiles(join(ROOT, 'src', 'components', d))),
  ...[...ROH_INFRA.keys()].map((f) => join(ROOT, f)),
]
const rohGesehen = new Map()
for (const f of new Set(rohScope)) {
  let src
  try { src = stripComments(readFileSync(f, 'utf8')) } catch { meld(`Roh-Sweep: Scope-Datei fehlt: ${rel(f)} — Scope/Freeze anpassen.`); continue }
  let m; let n = 0
  while ((m = ROH.exec(src)) !== null) {
    if (m[1] === 'input') {
      // `type="file"` ist legitim (keine SoT-Datei-Komponente) — Tag-Kopf prüfen.
      const ahead = src.slice(m.index, m.index + 400)
      const tagEnd = ahead.indexOf('>')
      if (/type=["']file/.test(ahead.slice(0, tagEnd < 0 ? 400 : tagEnd + 1))) continue
    }
    n++
  }
  if (n > 0) rohGesehen.set(rel(f), n)
}
for (const [file, n] of rohGesehen) {
  const erlaubt = ROH_REST.get(file) ?? ROH_INFRA.get(file) ?? 0
  if (n !== erlaubt) meld(`Roh-Controls: ${file} hat ${n}× (erlaubt: ${erlaubt}) — SoT-Komponente nutzen (§0.1 SoT-Map); bewusster Abbau → Freeze runterzählen.`)
}
for (const [file, erlaubt] of [...ROH_REST, ...ROH_INFRA]) {
  if (!rohGesehen.has(file) && erlaubt > 0) meld(`Roh-Controls: Freeze-Eintrag ohne Treffer: ${file} (erlaubt ${erlaubt}) — Eintrag entfernen (Abbau sichtbar machen).`)
}

// --- Ergebnis ---
if (fehler) {
  console.error(`\ncheck:v4-migration — ${fehler} Abweichung(en) vom eingefrorenen Migrationsstand (PLAN-V4-MAENGELBEHEBUNG.md).`)
  process.exit(1)
}
const restControls = [...ROH_REST.values()].reduce((a, b) => a + b, 0)
const restNav = [...NAVIGATE_ALLOW.values()].reduce((a, b) => a + b, 0)
console.log(
  `✓ check:v4-migration — Registry ${REGISTRY_MIGRIERT.size} migriert/${REGISTRY_REST.size} offen · ` +
  `navigate→V3 ${restNav} (${NAVIGATE_ALLOW.size} Dateien) · Roh-Controls ${restControls} in ${ROH_REST.size} Dateien offen ` +
  `(+ ${[...ROH_INFRA.values()].reduce((a, b) => a + b, 0)} Infra-freigegeben). Die Freeze-Listen sind die Rest-Arbeitsliste.`,
)
