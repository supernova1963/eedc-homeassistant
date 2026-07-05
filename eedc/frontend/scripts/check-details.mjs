#!/usr/bin/env node
/**
 * check-details.mjs — B6-Disclosure-Gate (Style-Guide B6/S9, R3b Etappe 3, 2026-07-05).
 *
 * Regel: Sub-Block-Disclosure per nativem `<details>` trägt EINEN Stil-Kanon —
 * `<details className="border-t border-gray-100 dark:border-gray-800 pt-3">` +
 * `<summary className="cursor-pointer text-sm text-gray-600 dark:text-gray-400
 * hover:text-gray-900 dark:hover:text-white">` + Summary-Formel „… anzeigen ({N})".
 *
 * Mechanik: zeilenbasiert (alle Vorkommen tragen die className einzeilig);
 * Klassen-Vergleich als Token-SET (Reihenfolge egal). Scope: src/v4/** +
 * V4-genutzte geteilte Dateien (Liste). V3-only-Altstellen (~9) bleiben bis zum
 * Flip außerhalb des Scopes.
 */
import { readdirSync, readFileSync, statSync, existsSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')

const GETEILTE_SOT = [
  'src/components/eauto/EAutoJahresvergleich.tsx',
  'src/components/balkonkraftwerk/BkwJahresvergleich.tsx',
  'src/components/speicher/SpeicherJahresbilanz.tsx',
  'src/components/speicher/SpeicherVerlaufCharts.tsx',
]

const DETAILS_KANON = new Set(['border-t', 'border-gray-100', 'dark:border-gray-800', 'pt-3'])
const SUMMARY_KANON = new Set([
  'cursor-pointer', 'text-sm', 'text-gray-600', 'dark:text-gray-400',
  'hover:text-gray-900', 'dark:hover:text-white',
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

const klassenSet = (zeile) => {
  const m = zeile.match(/className="([^"]*)"/)
  return m ? new Set(m[1].trim().split(/\s+/)) : null
}
const setGleich = (a, b) => a && a.size === b.size && [...b].every((t) => a.has(t))

let fehler = 0
for (const file of dateien) {
  const rel = relative(ROOT, file).replaceAll('\\', '/')
  const zeilen = readFileSync(file, 'utf8').split('\n')
  zeilen.forEach((z, i) => {
    // Kommentarzeilen (JSDoc/Zeilen-Kommentar) nicht als Markup werten.
    if (/^\s*(\*|\/\/|\{\/\*)/.test(z)) return
    if (/<details[\s>]/.test(z)) {
      if (!setGleich(klassenSet(z), DETAILS_KANON)) {
        fehler++
        console.error(`✗ ${rel}:${i + 1} — <details> weicht vom B6-Kanon ab (border-t border-gray-100 dark:border-gray-800 pt-3)`)
      }
    }
    if (/<summary[\s>]/.test(z)) {
      if (!setGleich(klassenSet(z), SUMMARY_KANON)) {
        fehler++
        console.error(`✗ ${rel}:${i + 1} — <summary> weicht vom B6-Kanon ab (cursor-pointer text-sm gray-600/400 + hover)`)
      }
      const inhalt = zeilen[i + 1] ?? ''
      if (!/ anzeigen \(/.test(z) && !/ anzeigen \(/.test(inhalt)) {
        fehler++
        console.error(`✗ ${rel}:${i + 1} — Summary ohne Kanon-Formel „… anzeigen ({N})"`)
      }
    }
  })
}

if (fehler) {
  console.error(`\ncheck:details — ${fehler} Abweichung(en) vom B6-Disclosure-Kanon.`)
  process.exit(1)
}
console.log('✅ B6/S9: <details>-Disclosures folgen dem EINEN Stil-Kanon (inkl. Summary-Formel).')
