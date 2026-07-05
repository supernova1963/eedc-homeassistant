#!/usr/bin/env node
/**
 * check-darkmode-paare.mjs — Dark-Mode-Paarungs-Gate (Style-Guide A8, R3b Etappe 1, 2026-07-05).
 *
 * Regel A8 (Text-Paarungen, de-facto-Kanon verbindlich): `text-gray-500` →
 * `dark:text-gray-400` (gedämpfter Text) · `text-gray-400` → `dark:text-gray-500`
 * (Muted/Icons — im Dark dezent DUNKLER, sonst zu hell auf Dunkelgrund).
 *
 * Geprüft werden die zwei drift-anfälligen Muted-Paarungen (400/500) in:
 *   (a) className-Literalen: Licht-Klasse ohne irgendeinen `dark:text-`-Partner
 *       im selben String = Verstoß (Paar-GENAUIGKEIT prüft der Wächter bewusst
 *       nicht — jeder dark:text-Partner zählt, wie im R3b-Audit-Auftrag).
 *   (b) `farbe:`-Props (BlockShell/FokusVollbild-Pfad): ungepaartes Literal
 *       überschreibt den korrekt gepaarten BlockShell-Default.
 *
 * Scope: src/v4/** + von V4 konsumierte geteilte Dateien (Liste unten).
 * Die übrigen A8-Paarungen (900/white, 700/300, 600/400) sind bewusst noch
 * nicht bewacht (Ausbau-Kandidat E3) — erst Bestand sichten, dann einfrieren.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SRC = join(ROOT, 'src')

const GETEILTE_SOT = [
  'src/components/aussicht/AussichtTeile.tsx',
  'src/components/balkonkraftwerk/BkwJahresvergleich.tsx',
  'src/components/eauto/EAutoJahresvergleich.tsx',
  'src/components/speicher/SpeicherJahresbilanz.tsx',
  'src/components/blocks/GrundlastSollIstKachel.tsx',
  'src/components/blocks/BlockShell.tsx',
  'src/components/blocks/FokusKachel.tsx',
  'src/components/werte/WerteTabelle.tsx',
]

/**
 * Dokumentierte Ausnahmen: Pfad → erlaubte Treffer-Zahl.
 *
 * Kontroll-Icon-Konvention (eingefroren, Entscheid-Kandidat R3b-E6): die v4-Block-
 * Kontroll-Icons (BlockShell ↑↓⤢⌄, Fokus-Schließen, Tabellen-Sortier-Pfeile) nutzen
 * bewusst `text-gray-400` als Basis in BEIDEN Modi + eigene dark:hover-Varianten —
 * konsistentes Muster aus dem BlockShell-SoT-Design, kein Drift. Ob es als
 * dokumentierte A8-Ausnahme in den Style-Guide kommt oder auf dark:text-gray-500
 * gedimmt wird, ist Maintainer-Entscheid (Etappe 3).
 */
const ALLOW = new Map([
  ['src/components/blocks/BlockShell.tsx', 4], // Kontroll-Icons (s. o.)
  ['src/components/blocks/FokusKachel.tsx', 1], // Fokus-Schließen-Icon (s. o.)
  ['src/components/werte/WerteTabelle.tsx', 2], // Sortier-Pfeile (s. o.)
  ['src/v4/CockpitLiveV4.tsx', 1], // Fokus-Kachel-Icon (s. o.)
])

function tsxFiles(dir) {
  const out = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    const s = statSync(p)
    if (s.isDirectory()) out.push(...tsxFiles(p))
    else if (name.endsWith('.tsx') && !name.endsWith('.test.tsx')) out.push(p)
  }
  return out
}

function lineOf(src, index) {
  return src.slice(0, index).split('\n').length
}

const CLASSNAME = /className=(?:"([^"]*)"|\{`([^`]*)`\})/gs
// Licht-Klasse der Muted-Paarungen, nicht selbst dark:/hover:-präfixiert.
const LICHT = /(?<![\w:-])text-gray-[45]00(?![\w-])/
const FARBE_PROP = /farbe:\s*'((?:[^']*\s)?text-gray-[45]00(?:\s[^']*)?)'/g

const dateien = [...tsxFiles(join(SRC, 'v4')), ...GETEILTE_SOT.map((f) => join(ROOT, f))]
const violations = []
let geprueft = 0

for (const file of new Set(dateien)) {
  const rel = relative(ROOT, file)
  const src = readFileSync(file, 'utf8')
  geprueft++
  const treffer = []
  let m
  while ((m = CLASSNAME.exec(src)) !== null) {
    const cls = m[1] ?? m[2]
    if (LICHT.test(cls) && !cls.includes('dark:text-')) treffer.push(`${lineOf(src, m.index)} (className)`)
  }
  while ((m = FARBE_PROP.exec(src)) !== null) {
    if (!m[1].includes('dark:')) treffer.push(`${lineOf(src, m.index)} (farbe-Prop)`)
  }
  const erlaubt = ALLOW.get(rel) ?? 0
  if (treffer.length > erlaubt) {
    violations.push(`${rel}: Z. ${treffer.join(' · ')}  [${treffer.length} Treffer, ${erlaubt} erlaubt]`)
  }
}

if (violations.length > 0) {
  console.error(`\n❌ check:darkmode-paare — ${violations.length} Datei(en) mit ungepaarten A8-Klassen:`)
  for (const v of violations) console.error('  · ' + v)
  console.error(
    '\nFix: text-gray-500 → +dark:text-gray-400 · text-gray-400 → +dark:text-gray-500. ' +
      'farbe-Props IMMER explizit paaren (Prop fließt in FokusVollbild ohne Grau-Default). ' +
      'Bewusste Ausnahme: Code-Kommentar + ALLOW-Eintrag (Regel 0a Stufe 3).',
  )
  process.exit(1)
}

console.log(`check:darkmode-paare — ${geprueft} Dateien geprüft, alle A8-Muted-Paarungen vollständig.`)
console.log('✅ A8: text-gray-400/500 überall mit dark:-Zwilling.')
