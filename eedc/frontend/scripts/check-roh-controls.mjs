#!/usr/bin/env node
/**
 * check-roh-controls.mjs — repo-weiter Roh-Control-Freeze (Regel 0a).
 *
 * Nachfolger des mit dem v4.0.0-Flip retired `check:v4-migration` (Teil 3,
 * Roh-Control-Sweep). Dessen Teile 1/2 (Registry-Freeze, navigate→V3) sind
 * post-flip gegenstandslos; die Roh-Control-Invariante „rohe Controls nur als
 * freigegebene SoT-/Infra-Implementierung" war seitdem über `pages/*` und die
 * Composite-Verzeichnisse UNGEWÄCHTERT — `check:buttons` deckt nur `<button>`
 * in `src/v4/**`, `check:form-controls` nur Nicht-Button-Controls in
 * `components/forms|setup-wizard/**` ([[feedback_v4_migration_status_control_ebene]]).
 *
 * Scope: ALLE .tsx unter `src/` (ohne Test-Dateien) — post-flip ist alles
 * user-erreichbar; bewusst KEINE Verzeichnis-Enumeration mehr (die war die
 * Scope-Loch-Quelle des Vorgängers). Muster/Mechanik 1:1 übernommen:
 * `<(button|select|input|textarea)(?![A-Za-z])`, Kommentare gestrippt,
 * `type="file"` ausgenommen (keine SoT-Datei-Komponente).
 *
 * Drei Freeze-Maps (Datei → exakte Treffer-Zahl; jede Abweichung — Zuwachs
 * ODER Abbau — muss die Liste hier anfassen):
 *   ROH_INFRA    — bewusste SoT-/Infra-Freigaben (Gernot 2026-07-11/17,
 *                  aus dem Vorgänger übernommen; Zählstände neu geeicht).
 *   ROH_BASELINE — Auffangbecken für künftige Scope-/Muster-Erweiterungen
 *                  (seit der Klassifizierungs-Runde 2026-07-25 leer).
 *   ROH_REST     — Migrationsschuld; die schrumpfende Liste IST die Arbeitsliste.
 *
 * `--inventur` gibt den Ist-Bestand als Map-Zeilen aus (zum Eichen/Klassifizieren).
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')

/** Bewusste SoT-/Infra-Freigaben (Vorgänger-ROH_INFRA, Gernot 2026-07-11/17).
 *  Zählstände 2026-07-25 neu geeicht — alle 31 identisch mit dem Alt-Freeze. */
const ROH_INFRA = new Map([
  ['src/components/ui/DatumPicker.tsx', 9], // SoT-Impl (Kalender-Grid-Buttons)
  ['src/components/ui/InlineAktion.tsx', 1], // SoT-Impl (Inline-Aktion/Disclosure)
  ['src/components/ui/SortableSection.tsx', 3], // SoT-Impl (Drag/Sort-Controls)
  ['src/components/DokumentationsDialog.tsx', 1], // Download-Karten-Kachel
  ['src/pages/InfothekTeile.tsx', 1], // Datei-Thumbnail-Kachel (→ Lightbox)
  ['src/components/infothek/DateiLightbox.tsx', 3], // Overlay-Mechanik X/‹/›
  ['src/components/infothek/DateiUpload.tsx', 1], // Thumbnail-Lösch-Overlay-Badge
  ['src/components/infothek/MarkdownNotizen.tsx', 3], // Editor-Toolbar + rahmenlose textarea
  ['src/components/blocks/BlockShell.tsx', 8], // Park/Fokus/Aufklapp-Mechanik
  ['src/components/park/GeparktBlock.tsx', 4], // Park-Mechanik
  ['src/components/layout/IATopNav.tsx', 4], // Navigation
  ['src/components/preview/IASkeleton.tsx', 11], // Dev-Preview (nicht user-erreichbar)
  ['src/v4/ZeitStepper.tsx', 3], // mobiler Zeit-Stepper
  ['src/v4/status/StatusFusszeile.tsx', 3], // Status-Fußzeilen-Chips
  ['src/v4/WerkbankZeitraum.tsx', 2], // Zeitraum-Schnellwahl-Chips
  ['src/v4/TagesRail.tsx', 1], // Rail-Eintrag
  ['src/v4/MonatsRail.tsx', 1], // Rail-Eintrag
  ['src/v4/JahresRail.tsx', 1], // Rail-Eintrag
  ['src/v4/TagesverlaufChart.tsx', 1], // Solo-Toggle „Autarkie %"
  ['src/v4/JahrVerlaufChart.tsx', 1], // Solo-Toggle „Autarkie %"
  ['src/v4/KomponentenTypV4.tsx', 1], // Geräte-Selektor-Pill
  ['src/v4/CockpitLiveV4.tsx', 1], // ⤢ Fokus-Button Energiefluss-Kartenkopf
  ['src/components/live/EnergieFluss.tsx', 2], // Live-Kartenkopf-Pillen
  ['src/components/werte/WerteTabelle.tsx', 2], // Spalten-Picker Reorder-Pfeile
  ['src/components/prognose/PrognoseVergleichTeile.tsx', 1], // ⚠-Popover-Trigger in Zelle
  ['src/pages/Einrichtung.tsx', 1], // Datenquellen-Karten-Kachel
  ['src/components/setup-wizard/steps/StrompreiseStep.tsx', 1], // Auswahl-Karte (mehrzeilig)
  ['src/components/setup-wizard/steps/InvestitionenStep.tsx', 3], // Schnellstart-Karte + Typ-Kacheln
  ['src/components/setup-wizard/sections/SetupInvestitionForm.tsx', 1], // Aufklapp-Header
  ['src/components/setup-wizard/sections/SetupInvestitionMenu.tsx', 1], // Dropdown-Menü-Einträge
  // ── Baseline-Klassifizierung 2026-07-25 (Gernot-Delegation „folge deiner
  //    Empfehlung"; Gattungs-Kriterien des Alt-Freeze) ──────────────────────
  // Gruppe 1 — ui/-SoT-Implementierungen (das rohe Control IST die SoT-Komponente):
  ['src/components/ui/Alert.tsx', 1],
  ['src/components/ui/BildUpload.tsx', 1],
  ['src/components/ui/Button.tsx', 1],
  ['src/components/ui/Checkbox.tsx', 1],
  ['src/components/ui/CollapsibleSection.tsx', 1],
  ['src/components/ui/CsvExportButton.tsx', 1],
  ['src/components/ui/DestructiveActionDialog.tsx', 2],
  ['src/components/ui/FormSection.tsx', 1],
  ['src/components/ui/Input.tsx', 1],
  ['src/components/ui/KPICard.tsx', 1],
  ['src/components/ui/Modal.tsx', 1],
  ['src/components/ui/RadioGroup.tsx', 1],
  ['src/components/ui/SegmentControl.tsx', 1],
  ['src/components/ui/Select.tsx', 1],
  ['src/components/ui/Slider.tsx', 1], // Schieberegler-SoT (2026-08-12, #358 Phase 3)
  ['src/components/ui/Stepper.tsx', 1],
  ['src/components/ui/Switch.tsx', 1],
  ['src/components/ui/Table.tsx', 1],
  ['src/components/ui/Textarea.tsx', 1],
  // Gruppe 2 — Shell-/Layout-/Park-Mechanik (Gattung BlockShell/IATopNav):
  ['src/components/blocks/FokusKachel.tsx', 1], // ⤢ Fokus-Icon (Gattung CockpitLiveV4)
  ['src/components/blocks/FokusVollbild.tsx', 1], // „Zurück" im Vollbild-Overlay
  // Gattungs-Bezug war `FeldMappingInput` — mit dem V3-Aufräumen 2026-08-13 gefallen;
  // diese Datei ist seither die einzige verbliebene Listbox-Combobox-Implementierung.
  ['src/components/layout/AnlagenSelektorView.tsx', 2],
  ['src/components/layout/IASubTabBar.tsx', 1], // Tab-Leisten-SoT selbst
  ['src/components/park/Parkbar.tsx', 2], // Park-Overlay-Mechanik (Gattung GeparktBlock)
  ['src/components/common/DataLoadingState.tsx', 1], // Retry im Fehlerzustand (Impl des geteilten Ladezustand-Bausteins)
  // Gruppe 3 — freigegebene Gattungen in Fach-Composites:
  ['src/components/import/custom/MappingTabelle.tsx', 1], // Invert-Mikro-Trigger in Zelle (Gattung ⚠-Popover)
  ['src/components/roi/RoiAnalyse.tsx', 1], // Zeilen-Disclosure in Tabelle
  ['src/components/tag/TagWerteTabelle.tsx', 2], // Spalten-Picker (Gattung WerteTabelle)
  ['src/pages/auswertung/EnergieprofilPrognose.tsx', 1], // „Morgen"-Schnellwahl-Chip (Gattung WerkbankZeitraum)
  // — REST-Abbau-Reste 2026-07-25 (Misch-Dateien, freigebbare Gattungen):
  ['src/pages/InvestitionenTeile.tsx', 2], // Typ-Karten-Kachel + Dropdown-Menü-Eintrag (Gattung SetupInvestitionMenu)
  ['src/pages/aussichten/KorrekturprofilHeatmapCard.tsx', 1], // Klassen-Tab-Chips (Gattung WerkbankZeitraum)
])

/** Scope-Ausweitungs-Baseline — seit der Klassifizierung 2026-07-25 leer
 *  (alle Einträge nach ROH_INFRA bzw. ROH_REST einsortiert); bleibt als
 *  Mechanik für künftige Scope-/Muster-Erweiterungen bestehen. */
const ROH_BASELINE = new Map([])

/** Migrationsschuld (Abbau-Arbeitsliste). Ziel: leer — Stand 2026-07-25: LEER.
 *  REST-Abbau-Runde 2026-07-25: 8 der 12 Dateien waren nach dem Flip toter Code
 *  (nirgends importiert) und wurden GELÖSCHT (ShareTextModal, EnergieprofilTab/
 *  -Monat, TabelleTab, EnergieTab, aussichten/{FinanzenTab,LangfristTab,TrendTab});
 *  die 4 lebenden wurden auf SoT migriert (Select/SegmentControl/Button/
 *  InlineAktion), ihre freigebbaren Gattungs-Reste stehen in ROH_INFRA.
 *  Bei künftigem Abbau in Misch-Dateien: freigebbare Gattungs-Reste (Chips/
 *  Nav-Pfeile/Kacheln) nach ROH_INFRA umziehen statt erzwungen migrieren. */
const ROH_REST = new Map([])

// ---------------------------------------------------------------------------

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

const ROH = /<(button|select|input|textarea)(?![A-Za-z])/g
const rohGesehen = new Map()
for (const f of tsxFiles(join(ROOT, 'src'))) {
  const src = stripComments(readFileSync(f, 'utf8'))
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

if (process.argv.includes('--inventur')) {
  for (const [file, n] of [...rohGesehen].sort()) console.log(`  ['${file}', ${n}],`)
  process.exit(0)
}

let fehler = 0
const meld = (msg) => { fehler++; console.error('✗ ' + msg) }

const erlaubtFuer = (file) => ROH_REST.get(file) ?? ROH_INFRA.get(file) ?? ROH_BASELINE.get(file) ?? 0
for (const [file, n] of rohGesehen) {
  const erlaubt = erlaubtFuer(file)
  if (n !== erlaubt) meld(`Roh-Controls: ${file} hat ${n}× (erlaubt: ${erlaubt}) — SoT-Komponente nutzen (Style-Guide §0.1 SoT-Map); bewusster Bestand/Abbau → Freeze hier anpassen.`)
}
for (const [file, erlaubt] of [...ROH_REST, ...ROH_INFRA, ...ROH_BASELINE]) {
  if (!rohGesehen.has(file) && erlaubt > 0) meld(`Roh-Controls: Freeze-Eintrag ohne Treffer: ${file} (erlaubt ${erlaubt}) — Eintrag entfernen (Abbau sichtbar machen).`)
}

if (fehler) {
  console.error(`\ncheck:roh-controls — ${fehler} Abweichung(en) vom eingefrorenen Roh-Control-Bestand.`)
  process.exit(1)
}
const sum = (m) => [...m.values()].reduce((a, b) => a + b, 0)
console.log(
  `✓ check:roh-controls — ${sum(ROH_REST)} Rest (${ROH_REST.size} Dateien) · ` +
  `${sum(ROH_INFRA)} Infra-freigegeben (${ROH_INFRA.size}) · ` +
  `${sum(ROH_BASELINE)} Baseline unklassifiziert (${ROH_BASELINE.size}). Die REST-/BASELINE-Listen sind die Arbeitsliste.`,
)
