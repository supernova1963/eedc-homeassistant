#!/usr/bin/env node
/**
 * check-chart-tooltip.mjs — Regel-D-Gate (B7/A6, R3b Etappe 3, 2026-07-05).
 *
 * Regel D (eedcTooltip.tsx, 2026-06-25): EINE Stelle setzt Hover-Cursor UND
 * ChartTooltip-Content — `<Tooltip {...eedcTooltipProps({...})} />`. Manuelles
 * Verdrahten ist der belegte Drift-Pfad (Cursor vergessen → Recharts-Default-
 * Grau, QS-1/QS-2) bzw. Struktur-Bypass (QS-6).
 *
 * Blockt unter src/v4/**: (a) `content={<ChartTooltip` als JSX-Attribut,
 * (b) `<Tooltip cursor=`-Handverdrahtung. Die Factory-Definition selbst matcht
 * NICHT (Objekt-Literal `content:` mit Doppelpunkt). V3-Altbestand (~80 Stellen)
 * bleibt außerhalb des Scopes bis zu den V3-Paketen/Flip.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SCOPE = join(ROOT, 'src', 'v4')

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

let fehler = 0
for (const file of tsxFiles(SCOPE)) {
  const rel = relative(ROOT, file).replaceAll('\\', '/')
  const zeilen = readFileSync(file, 'utf8').split('\n')
  zeilen.forEach((z, i) => {
    if (/^\s*(\*|\/\/|\{\/\*)/.test(z)) return
    if (/content=\{<ChartTooltip/.test(z)) {
      fehler++
      console.error(`✗ ${rel}:${i + 1} — ChartTooltip manuell verdrahtet — Regel D: <Tooltip {...eedcTooltipProps({…})} />`)
    } else if (/<Tooltip\s+cursor=/.test(z)) {
      fehler++
      console.error(`✗ ${rel}:${i + 1} — Hand-Cursor am Tooltip — Regel D: eedcTooltipProps setzt Cursor+Content zusammen`)
    }
  })
}

if (fehler) {
  console.error(`\ncheck:chart-tooltip — ${fehler} Regel-D-Bypass(e).`)
  process.exit(1)
}
console.log('✅ Regel D: alle v4-Chart-Tooltips laufen über die eedcTooltipProps-Factory.')
