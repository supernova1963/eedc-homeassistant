#!/usr/bin/env node
/**
 * check-status-icons.mjs — Status-Icon-SoT-Gate (Style-Guide B17/A5, R3b Etappe 1, 2026-07-05).
 *
 * Regel: Status-Icons (ok/warnung/kritisch/info) kommen aus **`STATUS_ICONS`**
 * (`lib/komponentenStyle.ts`) als EINER Quelle — kein Direkt-Import der Kanon-Icons
 * (CheckCircle/AlertTriangle/XCircle/Info) und keiner der bekannten Drift-Varianten
 * (CheckCircle2/AlertCircle/Sparkles) aus lucide-react in Sichten-Code.
 *
 * Scope: src/v4/** + von V4 konsumierte geteilte Dateien + IASkeleton (Preview-SoT,
 * Konvergenz-Prinzip). Allowlist = belegte NICHT-Status-Verwendungen (dekorativ).
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
  'src/components/preview/IASkeleton.tsx',
]

/**
 * Dokumentierte Ausnahmen: Pfad → erlaubte Treffer-Zahl.
 * CommunityUebersichtV4: `Sparkles` als DEKORATIVES Block-Themen-Icon des
 * Achievements-Blocks (kein Status-Kontext ok/warnung/kritisch/info) — belegte
 * Nicht-Status-Verwendung, kein Drift.
 */
const ALLOW = new Map([
  ['src/v4/CommunityUebersichtV4.tsx', 1],
])

const STATUS_NAMEN = ['CheckCircle', 'CheckCircle2', 'AlertTriangle', 'XCircle', 'AlertCircle', 'Info', 'Sparkles']

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

// lucide-Import-Blöcke (auch mehrzeilig) einsammeln, benannte Importe prüfen.
const LUCIDE_IMPORT = /import\s*(?:type\s*)?\{([^}]*)\}\s*from\s*'lucide-react'/gs

const dateien = [...tsxFiles(join(SRC, 'v4')), ...GETEILTE_SOT.map((f) => join(ROOT, f))]
const violations = []
let geprueft = 0

for (const file of new Set(dateien)) {
  const rel = relative(ROOT, file)
  const src = readFileSync(file, 'utf8')
  geprueft++
  const treffer = []
  let m
  while ((m = LUCIDE_IMPORT.exec(src)) !== null) {
    const namen = m[1].split(',').map((s) => s.trim().replace(/^type\s+/, '').split(/\s+as\s+/)[0])
    for (const n of namen) {
      if (STATUS_NAMEN.includes(n)) treffer.push(`${lineOf(src, m.index)} (${n})`)
    }
  }
  const erlaubt = ALLOW.get(rel) ?? 0
  if (treffer.length > erlaubt) {
    violations.push(`${rel}: Z. ${treffer.join(' · ')}  [${treffer.length} Treffer, ${erlaubt} erlaubt]`)
  }
}

if (violations.length > 0) {
  console.error(`\n❌ check:status-icons — ${violations.length} Datei(en) mit Status-Icon-Direkt-Importen:`)
  for (const v of violations) console.error('  · ' + v)
  console.error(
    '\nFix: STATUS_ICONS aus lib/komponentenStyle (via ../lib) nutzen — ok=CheckCircle, ' +
      'warnung=AlertTriangle, kritisch=XCircle, info=Info. Dekorative Nicht-Status-Verwendung: ' +
      'Code-Kommentar + ALLOW-Eintrag (Regel 0a Stufe 3).',
  )
  process.exit(1)
}

console.log(`check:status-icons — ${geprueft} Dateien geprüft, keine Status-Icon-Direkt-Importe außerhalb der Allowlist.`)
console.log('✅ B17/A5: Status-Icons kommen aus STATUS_ICONS (eine Quelle).')
