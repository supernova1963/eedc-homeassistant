#!/usr/bin/env node
/**
 * check-label-maps.mjs — Label-Map-SoT-Gate (Regel 0 / R3b Etappe 2 S7, 2026-07-05).
 *
 * Regel: Enum→Label-Maps und Wochentagsnamen leben EINMAL in `lib/constants.ts`
 * ([[feedback_typ_labels_pattern]]) — lokale Kopien driften (belegt: Provenance-Map
 * 3× mit fehlenden Keys → Roh-Enums in der UI; Wochentags-Arrays 7× mit DREI
 * Index-Semantiken). Der Wächter blockt Neu-Definitionen der zentralisierten
 * Vokabulare außerhalb der SoT:
 *  - Wochentags-Array-Literale (So-first, Mo-first, lang) → WT_KURZ/WT_LANG
 *    (Mo-first per Rotation `[...WT_KURZ.slice(1), WT_KURZ[0]]`)
 *  - Sonstiges-Kategorie-Map (`erzeuger: 'Erzeuger'`) → SONSTIGES_KATEGORIE_LABELS
 *  - Provenance-Map (`ha_sensor: 'HA'` …) → DATENQUELLE_LABELS
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SRC = join(ROOT, 'src')
const SOT = 'src/lib/constants.ts'

const MUSTER = [
  [/\[\s*'So'\s*,\s*'Mo'/, 'Wochentags-Array (So-first) — WT_KURZ aus lib/constants nutzen'],
  [/\[\s*'Mo'\s*,\s*'Di'/, "Wochentags-Array (Mo-first) — Rotation `[...WT_KURZ.slice(1), WT_KURZ[0]]` nutzen"],
  [/\[\s*'Sonntag'\s*,\s*'Montag'/, 'Wochentags-Array (lang) — WT_LANG aus lib/constants nutzen'],
  [/erzeuger:\s*'Erzeuger'/, 'Sonstiges-Kategorie-Map — SONSTIGES_KATEGORIE_LABELS nutzen'],
  [/ha_sensor:\s*'HA'/, 'Provenance-Map — DATENQUELLE_LABELS nutzen'],
]

/** Dokumentierte Ausnahmen: Pfad → erlaubte Treffer-Zahl (Bestand, mit Grund). */
const ALLOW = new Map([])

function files(dir) {
  const out = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    const s = statSync(p)
    if (s.isDirectory()) out.push(...files(p))
    else if (/\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name)) out.push(p)
  }
  return out
}

let fehler = 0
for (const file of files(SRC)) {
  const rel = relative(ROOT, file).replaceAll('\\', '/')
  if (rel === SOT) continue
  const src = readFileSync(file, 'utf8')
  let treffer = 0
  for (const [re, hinweis] of MUSTER) {
    if (re.test(src)) {
      treffer++
      if (treffer > (ALLOW.get(rel) ?? 0)) {
        fehler++
        console.error(`✗ ${rel} — lokale Kopie eines SoT-Vokabulars: ${hinweis}`)
      }
    }
  }
}

if (fehler) {
  console.error(`\ncheck:label-maps — ${fehler} lokale Map-Kopie(n) außerhalb lib/constants.ts.`)
  process.exit(1)
}
console.log('✅ Regel 0/S7: Label-Maps + Wochentage kommen aus lib/constants (keine lokalen Kopien).')
