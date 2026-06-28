#!/usr/bin/env node
/**
 * check-achsen.mjs — Abdeckungs-Garantie für Achsen-Einheiten (R9-Nacharbeit).
 *
 * Hintergrund: detLAN wies die Achsen-Runde zu Recht zurück — nur ein Bruchteil
 * der Charts trug eine Einheit, und die Platzierung kollidierte. Dieser Check
 * stellt sicher, dass JEDE Wert-Achse genau eine Einheit über `achsenEinheit(`
 * trägt ODER explizit als Kategorie-/Index-/Jahr-Achse freigegeben ist.
 *
 * Regel je Achse (`<YAxis …>` / `<XAxis …>`):
 *   • enthält `achsenEinheit(` im Tag  → Wert-Achse MIT Einheit  ✅
 *   • enthält Inline-Marker `achsen-allow: <Begründung>` im Tag → bewusst ohne
 *     Einheit (Kategorie/Index/Jahr/Sparkline …) ✅ (dokumentiert)
 *   • sonst → VERSTOSS ❌ (Exit 1)
 *
 * Ausgabe: "N/N Wert-Achsen mit Einheit (M Kategorie-/Index-Achsen in Allowlist)".
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SRC = join(ROOT, 'src')

/** Rekursiv alle .tsx (ohne Tests) einsammeln. */
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

/**
 * Extrahiert ab Index `start` (auf '<') den Text des öffnenden Tags bis zum
 * schließenden '>' auf Klammertiefe 0. Überspringt '=>' (Arrow-Funktionen in
 * Props wie `tickFormatter={(v) => …}`) und zählt `{}`-Tiefe mit.
 */
function openTag(src, start) {
  let depth = 0
  for (let i = start + 1; i < src.length; i++) {
    const c = src[i]
    if (c === '{') depth++
    else if (c === '}') depth--
    else if (c === '>' && depth === 0) {
      if (src[i - 1] === '=') continue // '=>' Arrow → kein Tag-Ende
      return src.slice(start, i + 1)
    }
  }
  return src.slice(start) // unbalanciert → ganzer Rest (fällt als Verstoß auf)
}

function findAxes(src) {
  const axes = []
  const re = /<(YAxis|XAxis)\b/g
  let m
  while ((m = re.exec(src)) !== null) {
    axes.push({ kind: m[1], tag: openTag(src, m.index), index: m.index })
  }
  return axes
}

function lineOf(src, index) {
  return src.slice(0, index).split('\n').length
}

let withUnit = 0
let allowed = 0
const violations = []
const tickViolations = []

for (const file of tsxFiles(SRC)) {
  const src = readFileSync(file, 'utf8')
  for (const ax of findAxes(src)) {
    const istWertAchse = ax.tag.includes('achsenEinheit(') || /achsen-allow:[^*]*Wert-Achse/.test(ax.tag)
    if (ax.tag.includes('achsenEinheit(')) withUnit++
    else if (/achsen-allow:/.test(ax.tag)) allowed++
    else violations.push(`${relative(ROOT, file)}:${lineOf(src, ax.index)} <${ax.kind}> ohne Einheit & ohne achsen-allow-Marker`)
    // de-DE-Pflicht: jede Wert-Achse braucht einen tickFormatter (achsenTick ODER
    // einen wert-transformierenden wie energieAchse/co2Achse/fmtZahl+€). Sonst
    // greift der Recharts-Default ohne Tausenderpunkt (R1-Verstoß, detLAN #29).
    if (istWertAchse && !ax.tag.includes('tickFormatter')) {
      tickViolations.push(`${relative(ROOT, file)}:${lineOf(src, ax.index)} <${ax.kind}> Wert-Achse ohne tickFormatter (kein de-DE/Tausenderpunkt)`)
    }
  }
}

const wertAchsen = withUnit + violations.length
console.log(
  `check:achsen — ${withUnit}/${wertAchsen} Wert-Achsen mit Einheit ` +
    `(${allowed} Kategorie-/Index-Achsen in Allowlist)`,
)

console.log(
  tickViolations.length === 0
    ? `check:achsen — alle Wert-Achsen mit de-DE tickFormatter`
    : `check:achsen — ${tickViolations.length} Wert-Achse(n) OHNE tickFormatter (kein Tausenderpunkt)`,
)

if (violations.length > 0 || tickViolations.length > 0) {
  if (violations.length > 0) {
    console.error(`\n❌ ${violations.length} Achse(n) ohne Einheit und ohne Allowlist-Marker:`)
    for (const v of violations) console.error('  · ' + v)
    console.error(
      '\nFix: Wert-Achse → `label={achsenEinheit(\'kWh\')}` (+ margin top: ACHSEN_MARGIN_TOP);' +
        '\n     Kategorie-/Jahr-/Index-Achse → Inline-Marker `/* achsen-allow: <Begründung> */` ins Tag.',
    )
  }
  if (tickViolations.length > 0) {
    console.error(`\n❌ ${tickViolations.length} Wert-Achse(n) ohne tickFormatter (Recharts-Default = kein Tausenderpunkt):`)
    for (const v of tickViolations) console.error('  · ' + v)
    console.error(
      '\nFix: `tickFormatter={achsenTick}` (de-DE, aus lib/chartAchse) ergänzen — ' +
        'AUSSER die Achse skaliert/€-formatiert bereits (energieAchse/co2Achse/fmtZahl+„ €").',
    )
  }
  process.exit(1)
}

console.log('✅ Alle Wert-Achsen tragen genau eine Einheit + de-DE tickFormatter.')
