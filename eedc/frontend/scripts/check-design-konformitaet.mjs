#!/usr/bin/env node
/**
 * Design-Konformitäts-Wächter (Regel 0/0a, VORBEREITUNG-E1-FUNDAMENT §10).
 *
 * Prüft: KEINE Inline-Hex-Farben in src/ außerhalb der Farb-Zentrale
 * (`src/lib/colors.ts`) und der freigegebenen Ausnahmen-Liste.
 *
 * Neuer Treffer => Exit 1. Der Weg ist dann (Regel 0a):
 *   1. Farb-Rolle in `lib/colors.ts` ergänzen/verwenden  (Normalfall)
 *   2. echte Einzelfall-Ausnahme: Maintainer-Freigabe einholen, Code-Kommentar
 *      an der Stelle + Eintrag UNTEN in AUSNAHMEN (mit Begründung + Datum)
 *
 * Aufruf: npm run check:design   (bzw. node scripts/check-design-konformitaet.mjs)
 * CI-Anbindung folgt mit der Frontend-Test-Infra (E1-P3).
 */

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const SRC = join(fileURLToPath(new URL('.', import.meta.url)), '..', 'src')

/** Freigegebene Ausnahmen (Pfad relativ zu src/) — nur mit Maintainer-Freigabe erweitern! */
const AUSNAHMEN = {
  'lib/colors.ts': 'Farb-Zentrale — die SoT selbst',
  'components/live/EnergieFlussBackground.tsx':
    'Szenische SVG-Hintergrund-Gradienten (Sunset/Alps/Nebula …) — thematische Kunst, ' +
    'keine semantischen Farben. Freigabe: VORBEREITUNG-E1-FUNDAMENT §6/§10 (Gernot, 2026-06-12)',
}

// 6-/8-stellige Hex immer; 3-/4-stellige nur direkt in Quotes UND mit mind. einem
// Buchstaben (sonst False-Positives durch Issue-Referenzen wie "#290" in Kommentaren;
// rein numerische Kurz-Hex wie '#000' werden bewusst nicht erkannt — dokumentierter Trade-off).
const HEX_LANG = /#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?\b/g
const HEX_KURZ = /(['"`])(#(?=[0-9a-fA-F]{0,3}[a-fA-F])[0-9a-fA-F]{3,4})\b/g

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) yield* walk(p)
    else if (/\.(ts|tsx)$/.test(name)) yield p
  }
}

const funde = []
for (const file of walk(SRC)) {
  const rel = relative(SRC, file).replaceAll('\\', '/')
  if (AUSNAHMEN[rel]) continue
  const lines = readFileSync(file, 'utf-8').split('\n')
  lines.forEach((line, i) => {
    const treffer = [
      ...line.matchAll(HEX_LANG),
      ...[...line.matchAll(HEX_KURZ)].map(m => ({ 0: m[2], index: m.index })),
    ]
    for (const t of treffer) funde.push({ rel, zeile: i + 1, wert: t[0], kontext: line.trim().slice(0, 100) })
  })
}

if (funde.length === 0) {
  console.log('✓ Design-Konformität: keine Inline-Hex-Farben außerhalb der Farb-Zentrale.')
  process.exit(0)
}

const proDatei = new Map()
for (const f of funde) {
  if (!proDatei.has(f.rel)) proDatei.set(f.rel, [])
  proDatei.get(f.rel).push(f)
}
console.error(`✗ ${funde.length} Inline-Hex-Fundstellen in ${proDatei.size} Dateien außerhalb der Farb-Zentrale:\n`)
for (const [rel, liste] of [...proDatei.entries()].sort((a, b) => b[1].length - a[1].length)) {
  console.error(`  ${rel} (${liste.length})`)
  for (const f of liste.slice(0, 8)) console.error(`    ${f.zeile}: ${f.wert}  ${f.kontext}`)
  if (liste.length > 8) console.error(`    … +${liste.length - 8} weitere`)
}
console.error('\nRegel 0a: Farb-Rolle in lib/colors.ts ergänzen/verwenden — oder Maintainer-Freigabe + Ausnahmen-Eintrag.')
process.exit(1)
