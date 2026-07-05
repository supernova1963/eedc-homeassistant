#!/usr/bin/env node
/**
 * check-typografie.mjs — Typografie-Skalen-Gate (Style-Guide A1, R3b Etappe 1, 2026-07-05).
 *
 * Regel A1: 9-Stufen-Skala (display=text-3xl … caption=text-[11px]) + v4-Zusatz-Zeilen
 * (titel-sicht=text-lg font-bold · titel-block=text-sm font-semibold · micro=text-[10px]).
 * Grep-bar davon:
 *   (a) `text-4xl`/`text-5xl`/`text-6xl+` — oberhalb der Skala (einzige dokumentierte
 *       Ausnahme text-5xl liegt in AktuellerMonat.tsx = V3, außerhalb des Scopes)
 *   (b) `text-xl` — existiert in KEINER Skalen-Zeile (title-xl = text-2xl!)
 *   (c) arbiträre Pixel-Größen `text-[Npx]` außer 10/11 px (micro/caption)
 * NICHT grep-bar (bewusst unbewacht): Rollen-Zuordnung von text-lg font-bold u. ä. —
 * das prüft der Konformitäts-Sweep, nicht dieses Gate.
 *
 * Scope: src/v4/** + von V4 konsumierte geteilte Dateien. Allowlist = dokumentierte
 * Ausnahmen (Regel 0a Stufe 3, Code-Kommentar an der Stelle).
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

/** Dokumentierte Ausnahmen: Pfad → erlaubte Treffer-Zahl. */
const ALLOW = new Map([])

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

const MUSTER = [
  { re: /text-[456]xl/g, was: 'oberhalb der Skala (display = text-3xl ist Maximum)' },
  { re: /(?<![\w-])text-xl(?![\w-])/g, was: 'text-xl ist keine Skalen-Zeile (title-xl = text-2xl)' },
  { re: /text-\[(?!10px\]|11px\])\d+px\]/g, was: 'arbiträre Pixel-Größe (Skala: nur text-[10px]/text-[11px])' },
]

const dateien = [...tsxFiles(join(SRC, 'v4')), ...GETEILTE_SOT.map((f) => join(ROOT, f))]
const violations = []
let geprueft = 0

for (const file of new Set(dateien)) {
  const rel = relative(ROOT, file)
  const src = readFileSync(file, 'utf8')
  geprueft++
  const treffer = []
  for (const mu of MUSTER) {
    let m
    mu.re.lastIndex = 0
    while ((m = mu.re.exec(src)) !== null) treffer.push(`${lineOf(src, m.index)} (${mu.was})`)
  }
  const erlaubt = ALLOW.get(rel) ?? 0
  if (treffer.length > erlaubt) {
    violations.push(`${rel}: Z. ${treffer.join(' · ')}  [${treffer.length} Treffer, ${erlaubt} erlaubt]`)
  }
}

if (violations.length > 0) {
  console.error(`\n❌ check:typografie — ${violations.length} Datei(en) außerhalb der A1-Skala:`)
  for (const v of violations) console.error('  · ' + v)
  console.error(
    '\nFix: auf Skalen-Stufe ziehen (Hero = text-3xl font-bold · Sektion = text-lg font-semibold · ' +
      'Mikro = text-[10px]). Bewusste Ausnahme: Code-Kommentar + ALLOW-Eintrag (Regel 0a Stufe 3).',
  )
  process.exit(1)
}

console.log(`check:typografie — ${geprueft} Dateien geprüft, alle Größen auf der A1-Skala.`)
console.log('✅ A1: keine Klassen oberhalb/außerhalb der Typografie-Skala.')
