#!/usr/bin/env node
/**
 * check-badges.mjs — Badge-/Chip-/Pill-Gate (Style-Guide B17, R3b Etappe 1, Gernot 2026-07-05).
 *
 * Regel B17: Badges/Chips/Pills = Form `rounded-full` oder `rounded-lg`, `text-xs`
 * (Mikro-Badges: `text-[10px]` laut A1-`micro`-Zeile), dezente Tönung
 * `bg-{c}-50 dark:bg-{c}-900/20` (+ `text-{c}-700 dark:text-{c}-300`), kein ALL-CAPS.
 * Neutral-Grau-Badges: `bg-gray-50 … dark:bg-gray-700` (die /20-Schablone ist für
 * Farbtöne — auf gray-800-Karten wäre sie unsichtbar; R3b-Verify-Konsens 2026-07-05).
 *
 * Heuristik: Badge-Kapsel = className-String mit `px-*` UND `py-0.5|py-1` (Karten
 * nutzen p-4/p-6, Buttons min-h — bleiben außen vor). In einer Kapsel sind Verstöße:
 *   (a) bloßes `rounded` (ohne -full/-lg/-md-Suffix)
 *   (b) satte Tönung `bg-{c}-100|200` (hover:-Zustände ausgenommen)
 *   (c) dunkle Tönung `dark:bg-{c}-900/30|40|50` (statt /20)
 *   (d) `uppercase` (ALL-CAPS verboten)
 *
 * Scope: src/v4/** + die von V4 konsumierten geteilten Dateien (Liste unten).
 * Allowlist: Pfad → erlaubte Treffer-Zahl (bewusste, dokumentierte Ausnahmen).
 * V3-geteilte Dateien (z. B. ui/QuelleBadge.tsx) sind bewusst NICHT im Scope —
 * sie kommen mit den V3-Umstellungs-Paketen (236 geparkte Funde, R3b-Plan).
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SRC = join(ROOT, 'src')

/** Von V4 konsumierte geteilte Dateien ohne V3-Nutzung (R3b-Import-Graph). */
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

// className-Literale (statisch + Template-Strings; Template-Ausdrücke bleiben drin,
// die Muster unten matchen nur echte Klassen-Literale).
const CLASSNAME = /className=(?:"([^"]*)"|\{`([^`]*)`\})/gs
const IST_KAPSEL = (cls) => /(?:^|\s)px-[\d.[]/.test(cls) && /(?:^|\s)py-(?:0\.5|1)(?:\s|$)/.test(cls)
const VERSTOESSE = [
  { re: /(?:^|[\s{$])rounded(?=\s|$)/, was: 'bloßes `rounded` (Form: rounded-full|lg)' },
  { re: /(?<!hover:)(?<!focus:)bg-[a-z]+-(?:100|200)\b/, was: 'satte Tönung bg-{c}-100/200 (Regel: bg-{c}-50)' },
  { re: /dark:bg-[a-z]+-900\/(?:30|40|50)\b/, was: 'dunkle Tönung /30|/40 (Regel: /20)' },
  { re: /(?:^|\s)uppercase(?:\s|$)/, was: 'ALL-CAPS (Casing wie Fließtext)' },
]

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
    if (!IST_KAPSEL(cls)) continue
    // Element-Kontext: <button>-Kapseln sind B15-Domäne (eigener Wächter), keine Badges.
    const tagStart = src.lastIndexOf('<', m.index)
    const tag = tagStart >= 0 ? /^<([a-zA-Z0-9]+)/.exec(src.slice(tagStart, m.index))?.[1] : null
    if (tag === 'button') continue
    for (const v of VERSTOESSE) {
      if (v.re.test(cls)) treffer.push(`${lineOf(src, m.index)} (${v.was})`)
    }
  }
  const erlaubt = ALLOW.get(rel) ?? 0
  if (treffer.length > erlaubt) {
    violations.push(`${rel}: Z. ${treffer.join(' · ')}  [${treffer.length} Treffer, ${erlaubt} erlaubt]`)
  }
}

if (violations.length > 0) {
  console.error(`\n❌ check:badges — ${violations.length} Datei(en) mit B17-Badge-Verstößen:`)
  for (const v of violations) console.error('  · ' + v)
  console.error(
    '\nFix: Form rounded-full|lg · Tönung bg-{c}-50 dark:bg-{c}-900/20 (Grau: dark:bg-gray-700) · ' +
      'kein uppercase. Bewusste Ausnahme: Code-Kommentar + ALLOW-Eintrag hier (Regel 0a Stufe 3).',
  )
  process.exit(1)
}

console.log(`check:badges — ${geprueft} Dateien geprüft, keine B17-Badge-Verstöße außerhalb der Allowlist.`)
console.log('✅ B17: Badges/Chips/Pills in Form, Tönung und Casing regelkonform.')
