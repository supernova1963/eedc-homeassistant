#!/usr/bin/env node
/**
 * check-persistenz.mjs — Persistenz-Konventions-Gate (Style-Guide C4, Gernot 2026-07-03).
 *
 * Regel: NEUER Code greift nicht direkt auf `localStorage` zu — Persistenz läuft
 * über die SoT-Module (ThemeContext `eedc-theme`, BlockShell `eedc-bloecke:` …),
 * Keys folgen dem Schema `eedc-<bereich>[:<sicht/zweck>]` (Bindestrich).
 *
 * Mechanik = Freeze-Gate: die Bestandsliste unten ist der eingefrorene Ist-Stand
 * (2026-07-03, Treffer-Anzahl pro Datei). Jede NEUE Datei mit `localStorage` und
 * jeder ZUWACHS in einer Bestandsdatei schlägt an → bewusste Entscheidung nötig
 * (SoT nutzen, oder Eintrag hier anpassen = dokumentierte Freigabe). Weniger
 * Treffer als eingefroren ist erlaubt (Abbau) — die Zahl hier dann mitsenken.
 *
 * **Austrag erledigt (2026-08-13, V3-Aufräumen):** `Layout`, `MonatsabschlussView`,
 * `CommunityShare` und `EnergieprofilTageTabelle` sind mit dem Flip gefallen, ihre
 * Bestands-Einträge hier entfernt. `CollapsibleSection`/`SortableSection` leben
 * weiter und bleiben mit ihrem Cap-Entscheid stehen.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SRC = join(ROOT, 'src')

/** SoT-Module: hier LEBT die Persistenz — Zugriff per Definition erlaubt. */
const SOT = new Set([
  'src/context/ThemeContext.tsx', // eedc-theme
  'src/components/blocks/BlockShell.tsx', // eedc-bloecke:<sichtKey> (Auf/Zu + Reihenfolge)
])

/** Eingefrorener Bestand (Datei → max. erlaubte `localStorage`-Treffer, Stand 2026-07-03). */
const BESTAND = new Map([
  ['src/components/AppWithSetup.tsx', 6],
  ['src/components/blocks/types.ts', 1],
  ['src/components/live/EnergieFluss.tsx', 4],
  ['src/components/live/WetterWidget.tsx', 3],
  ['src/components/park/ParkContext.tsx', 4],
  ['src/components/tag/TagWerteTabelle.tsx', 4],
  ['src/components/ui/CollapsibleSection.tsx', 3], // LEGACY V3 (Persistenz-SoT-Doppel → Cap-Entscheid 2026-06-01)
  ['src/components/ui/SortableSection.tsx', 4], // LEGACY V3 (dito)
  ['src/components/werte/WerteTabelle.tsx', 7],
  ['src/hooks/useSectionOrder.ts', 5],
  // 5 → 6 am 17.08.2026 (N-265): `removeItem`. Der Key wurde bis dahin
  // geschrieben, aber NIE geräumt — wer seine einzige Anlage löschte, behielt
  // eine tote ID, die jeder Schreibpfad als gültige Auswahl weiterreichte.
  // Das Räumen gehört genau hierher: diese Datei IST der SoT der Anlagenwahl.
  ['src/hooks/useSelectedAnlage.ts', 6],
  ['src/hooks/useSetupWizard.ts', 3],
  ['src/pages/MonatsdatenTeile.tsx', 2],
  ['src/v4/AnlagenSelektor.tsx', 1],
])

function srcFiles(dir) {
  const out = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    const s = statSync(p)
    if (s.isDirectory()) out.push(...srcFiles(p))
    else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name)) out.push(p)
  }
  return out
}

const violations = []
let dateienMitZugriff = 0

for (const file of srcFiles(SRC)) {
  const rel = relative(ROOT, file)
  const treffer = (readFileSync(file, 'utf8').match(/localStorage/g) ?? []).length
  if (treffer === 0) continue
  dateienMitZugriff++
  if (SOT.has(rel)) continue
  const erlaubt = BESTAND.get(rel) ?? 0
  if (treffer > erlaubt) {
    violations.push(`${rel}  (${treffer} Treffer, ${erlaubt} eingefroren)`)
  }
}

if (violations.length > 0) {
  console.error(`\n❌ check:persistenz — ${violations.length} Datei(en) mit neuem direktem localStorage-Zugriff (C4-Verstoß):`)
  for (const v of violations) console.error('  · ' + v)
  console.error(
    '\nFix: Persistenz über die SoT-Module (ThemeContext, BlockShell) bzw. bestehende ' +
      'Hooks; Keys nach Schema `eedc-<bereich>[:<zweck>]`. Bewusste Ausnahme = ' +
      'BESTAND-Eintrag hier anpassen (dokumentierte Freigabe).',
  )
  process.exit(1)
}

console.log(`check:persistenz — ${dateienMitZugriff} Dateien mit localStorage, alle SoT/eingefroren (kein Neuzugang).`)
console.log('✅ C4: keine neue Streu-Persistenz außerhalb der SoT-Module.')
