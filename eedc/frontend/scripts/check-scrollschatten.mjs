#!/usr/bin/env node
/**
 * check-scrollschatten.mjs — Überlauf-Affordanz-Gate (Style-Guide A9, Gernot 2026-07-03).
 *
 * Regel: Inhalts-Container zeigen Überlauf per ScrollSchatten-Fade (SoT
 * `components/ui/ScrollSchatten.tsx`), NICHT per sichtbarem Scroll-Balken.
 * Roher `overflow-(x-|y-)auto` unter `src/v4/**` (+ den von V4 konsumierten
 * geteilten SoT-Komponenten) ist ein Verstoß.
 *
 * Allowlist = dokumentierte Ausnahmen (Regel 0a Stufe 3, Code-Kommentar an der
 * Stelle): SEITEN-/SICHT-Scroller behalten den nativen Balken — der Fade gilt
 * für Inhalts-Container (Tabellen, Rails, Leisten), nicht die Seite selbst.
 * Format: Pfad → erlaubte Treffer-Anzahl (ein NEUER roher overflow in einer
 * Allowlist-Datei schlägt trotzdem an).
 *
 * Bewusst NICHT im Scope: V3-only-Seiten (sterben am Flip — kein Sweep an
 * Totem) und Overlay-SoTs mit Seiten-Charakter (Modal = eigener Viewport).
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SRC = join(ROOT, 'src')

/** Dokumentierte Ausnahmen: Pfad (relativ zu ROOT) → erlaubte Anzahl roher overflow-auto. */
const ALLOW = new Map([
  ['src/v4/LayoutV4.tsx', 1], // Seiten-Scroller (main) — nativer Balken bleibt
  ['src/v4/ViewShell.tsx', 1], // Sicht-Scroller ab lg (data-sicht-scroll) — dito
  ['src/components/blocks/FokusVollbild.tsx', 1], // Vollbild-Overlay = Seite im Fokus-Modus
])

/** Geteilte SoT-Komponenten außerhalb src/v4/, die V4 konsumiert (Regel gilt dort mit). */
const GETEILTE_SOT = [
  'src/components/werte/WerteTabelle.tsx',
  'src/components/ui/Table.tsx',
  'src/components/blocks/FokusVollbild.tsx',
  'src/components/blocks/BlockShell.tsx',
  // R3b Etappe 1 (2026-07-05): V4-only-geteilte Inhalts-Container aus dem
  // Konformitäts-Sweep (A9-Rest) — auf ScrollSchatten umgestellt, hier bewacht.
  'src/components/aussicht/AussichtTeile.tsx',
  'src/components/balkonkraftwerk/BkwJahresvergleich.tsx',
  'src/components/eauto/EAutoJahresvergleich.tsx',
  'src/components/speicher/SpeicherJahresbilanz.tsx',
]

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

// Roher Auto-Overflow als Tailwind-Klasse (auch mit Breakpoint-Prefix wie lg:).
const RAW_OVERFLOW = /overflow-(?:[xy]-)?auto/g

const dateien = [...tsxFiles(join(SRC, 'v4')), ...GETEILTE_SOT.map((f) => join(ROOT, f))]
const violations = []
let geprueft = 0

for (const file of new Set(dateien)) {
  const rel = relative(ROOT, file)
  const src = readFileSync(file, 'utf8')
  geprueft++
  const treffer = []
  let m
  while ((m = RAW_OVERFLOW.exec(src)) !== null) treffer.push(lineOf(src, m.index))
  const erlaubt = ALLOW.get(rel) ?? 0
  if (treffer.length > erlaubt) {
    violations.push(`${rel}:${treffer.join(',')}  (${treffer.length} roh, ${erlaubt} erlaubt)`)
  }
}

if (violations.length > 0) {
  console.error(`\n❌ check:scrollschatten — ${violations.length} Datei(en) mit rohem overflow-auto (A9-Verstoß):`)
  for (const v of violations) console.error('  · ' + v)
  console.error(
    '\nFix: Container in `<ScrollSchatten achse=… fadeFrom=…>` wrappen (SoT ' +
      '`components/ui/ScrollSchatten.tsx`; Karten-Fläche: `from-white dark:from-gray-800`). ' +
      'Echte Seiten-/Sicht-Scroller: Ausnahme mit Code-Kommentar + ALLOW-Eintrag hier.',
  )
  process.exit(1)
}

console.log(`check:scrollschatten — ${geprueft} Dateien geprüft, kein roher overflow-auto außerhalb der Allowlist.`)
console.log('✅ A9: Überlauf zeigt ScrollSchatten-Fade statt Scroll-Balken.')
