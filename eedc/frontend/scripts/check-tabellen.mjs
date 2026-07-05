#!/usr/bin/env node
/**
 * check-tabellen.mjs — B2-Tabellen-Gate (Style-Guide B2, R3b Etappe 2, 2026-07-05).
 *
 * Zwei grep-bare B2-Regeln:
 *  1. Spalten-Header-Farbe = `text-gray-500 dark:text-gray-400` — die gedrehte
 *     (hellere) Paarung `text-gray-400 dark:text-gray-500` auf einer Header-`<tr`
 *     ist der S13-Drift und blockt.
 *  2. Einheit im Header in RUNDEN Klammern `Name (Einheit)` — eckige Einheiten-
 *     Klammern (`[kWh]`, `[{einheit}]` …) in `<th`-Zeilen blocken.
 *
 * Scope: src/v4/** + von V4 konsumierte geteilte Tabellen-Dateien + IASkeleton
 * (Preview-SoT, Konvergenz-Prinzip — war der Drift-Ursprung von S13).
 */
import { readdirSync, readFileSync, statSync, existsSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')

const GETEILTE_SOT = [
  'src/components/werte/WerteTabelle.tsx',
  'src/components/werte/TagWerteTabelle.tsx',
  'src/components/aussicht/AussichtTeile.tsx',
  'src/components/balkonkraftwerk/BkwJahresvergleich.tsx',
  'src/components/balkonkraftwerk/BkwCharts.tsx',
  'src/components/eauto/EAutoJahresvergleich.tsx',
  'src/components/speicher/SpeicherJahresbilanz.tsx',
  'src/components/preview/IASkeleton.tsx',
]

/** Dokumentierte Ausnahmen: Pfad → erlaubte Treffer-Zahl je Regel-Schlüssel. */
const ALLOW = new Map([
  // TagWerteTabelle (V3-Ära-Vorlage) trägt den Muted-Header noch — Angleichung
  // kommt mit den V3-Paketen (Allowlist = Rest-Bestand sichtbar).
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

const dateien = [
  ...tsxFiles(join(ROOT, 'src', 'v4')),
  ...GETEILTE_SOT.map((r) => join(ROOT, r)).filter((p) => existsSync(p)),
]

let fehler = 0
for (const file of dateien) {
  const rel = relative(ROOT, file).replaceAll('\\', '/')
  const zeilen = readFileSync(file, 'utf8').split('\n')
  const erlaubt = ALLOW.get(rel) ?? 0
  let treffer = 0
  zeilen.forEach((z, i) => {
    if (/<tr\b[^>]*className="[^"]*text-gray-400 dark:text-gray-500/.test(z)) {
      treffer++
      if (treffer > erlaubt) {
        fehler++
        console.error(`✗ ${rel}:${i + 1} — Header-Farbe gedreht (text-gray-400 dark:text-gray-500) — B2: text-gray-500 dark:text-gray-400`)
      }
    }
    if (/<th\b/.test(z) && /\[\s*(?:\{?\s*einheit\s*\}?|kWh|kW|%|€|ct)\s*\]/.test(z)) {
      fehler++
      console.error(`✗ ${rel}:${i + 1} — Einheit in eckigen Klammern im Header — B2: Format „Name (Einheit)"`)
    }
  })
}

if (fehler) {
  console.error(`\ncheck:tabellen — ${fehler} B2-Verstoß/Verstöße (Header-Farbe/Klammer-Format).`)
  process.exit(1)
}
console.log('✅ B2: Tabellen-Header in Kanon-Farbe (gray-500/400) und rundem Einheiten-Klammer-Format.')
