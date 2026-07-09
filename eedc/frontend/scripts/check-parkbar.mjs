#!/usr/bin/env node
/**
 * check-parkbar.mjs — Wächter der Element-Park-Doktrin (Gernot 2026-07-09).
 *
 * Doktrin: EINE `<Parkbar>` umhüllt GENAU EINE atomare Anzeige (ein Chart / eine
 * Tabelle / eine Kachel / eine Liste / ein Hinweis) — NIE ein Bündel aus mehreren
 * eigenständigen Anzeigen (Referenz-Bug: eine `<Parkbar>` um `<MonatBilanz>`, das
 * intern Tabelle + Kachel + Balken + Hinweis rendert).
 *
 * Da „ist das Kind atomar?" nicht grep-bar ist, arbeitet der Wächter als **Allowlist-
 * Tripwire** (vom Maintainer gewählte Form): jede `<Parkbar>`-Umhüllung wird auf ihr
 * unmittelbares Kind reduziert (Komponentenname bzw. `div`/`dl`/`{DYN}`…). Steht das
 * Kind NICHT in `scripts/parkbar-allowlist.json`, schlägt der Check an — das zwingt
 * bei jeder NEU umhüllten (oft: benannten Composite-)Komponente zur bewussten Frage
 * „rendert sie GENAU EINE Anzeige?". Ist sie atomar → in die Allowlist aufnehmen; ist
 * sie ein Bündel → in Einzel-Parkbars zerlegen (Speicher-Muster).
 *
 * Grenze (bewusst): generische Wrapper (`div`/`dl`/`p`) kann der Wächter nicht nach
 * innen prüfen — sie sind allowlisted; der echte Tripwire ist die neue benannte
 * Komponente. Nicht perfekt, aber fängt die real aufgetretene Drift.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SRC = join(ROOT, 'src')
const ALLOWLIST = new Set(JSON.parse(readFileSync(join(ROOT, 'scripts', 'parkbar-allowlist.json'), 'utf8')))

function files(dir) {
  const out = []
  for (const n of readdirSync(dir)) {
    const p = join(dir, n)
    const s = statSync(p)
    if (s.isDirectory()) out.push(...files(p))
    else if (n.endsWith('.tsx') && !n.includes('.test.')) out.push(p)
  }
  return out
}

/** Das unmittelbare Kind hinter dem öffnenden `<Parkbar …>`-Tag. */
function kindHinter(rest) {
  const s = rest.replace(/^\s+/, '')
  if (s.startsWith('{')) return '{DYN}'
  const t = s.match(/^<([A-Za-z][\w.]*)/)
  return t ? t[1] : '{TEXT}'
}

const reOpen = /<Parkbar\b[\s\S]*?>/g
const verstoesse = []
let gesamt = 0

for (const f of files(SRC)) {
  const src = readFileSync(f, 'utf8')
  let m
  while ((m = reOpen.exec(src))) {
    gesamt++
    const kind = kindHinter(src.slice(m.index + m[0].length))
    if (!ALLOWLIST.has(kind)) {
      const zeile = src.slice(0, m.index).split('\n').length
      verstoesse.push({ datei: f.replace(ROOT + '/', ''), zeile, kind })
    }
  }
}

if (verstoesse.length > 0) {
  console.error('\ncheck:parkbar — NEUE Parkbar-Umhüllung(en) außerhalb der Allowlist:\n')
  for (const v of verstoesse) console.error(`  ✗ ${v.datei}:${v.zeile} → <Parkbar> um \`${v.kind}\``)
  console.error(
    '\nDoktrin: eine <Parkbar> = GENAU EINE atomare Anzeige (kein Bündel).\n' +
    'Prüfe die Komponente: rendert sie mehrere eigenständige Anzeigen?\n' +
    '  • JA  → in Einzel-Parkbars zerlegen (Speicher-Muster: KpiStrip parkId + je Element eine Parkbar).\n' +
    '  • NEIN (eine Anzeige) → Namen in scripts/parkbar-allowlist.json aufnehmen.\n',
  )
  process.exit(1)
}

console.log(`\ncheck:parkbar — ${gesamt} <Parkbar>-Umhüllungen, alle in der Allowlist (${ALLOWLIST.size} bekannt-atomare Kinder).`)
console.log('✅ Element-Park-Doktrin: keine unbestätigte Parkbar-Umhüllung (kein Composite-Bündel eingeschmuggelt).')
