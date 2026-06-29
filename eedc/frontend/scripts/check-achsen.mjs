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
const sizeViolations = []
const dropViolations = []

// Akzeptierte Formen einer 10-px-Tick-Deklaration (ACHSEN_TICK-SoT). Spreads
// `xAchse(`/`yAchse(` setzen tick:ACHSEN_TICK; `tick={(` ist ein Custom-Renderer
// (regelt fontSize selbst); `tick={false}`/`hide` = Achse ohne Ticks.
const TICK_10 = /ACHSEN_TICK|xAchse\(|yAchse\(|fontSize:\s*10\b|fontSize=\{10\}|tick=\{\(|tick=\{false\}|\bhide\b/
// Label-Drop: `… ? achsenEinheit(…) : undefined|null` lässt die Einheit ganz
// verschwinden (D11-14: Y-Achse ohne Einheit). Die Einheit muss garantiert sein.
const LABEL_DROP = /\?\s*achsenEinheit\([^)]*\)\s*:\s*(undefined|null)/

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
    // Tick-GRÖSSE: JEDE Achse muss 10 px tragen (ACHSEN_TICK-SoT). Fehlt die
    // Deklaration, fällt Recharts auf 12 px → Größen-Drift (D11-6/D11-7: 2. Achse
    // größer als die 1.). Genau die Lücke, die detLAN #29/#39 fand.
    if (!TICK_10.test(ax.tag)) {
      sizeViolations.push(`${relative(ROOT, file)}:${lineOf(src, ax.index)} <${ax.kind}> ohne 10-px-Tick (Recharts-Default 12 px = Größen-Drift)`)
    }
    // Label-DROP: bedingte Einheit, die zu undefined/null kollabiert → Achse ohne
    // Einheit (D11-14). Einheit immer setzen (notfalls Fallback statt Drop).
    if (LABEL_DROP.test(ax.tag)) {
      dropViolations.push(`${relative(ROOT, file)}:${lineOf(src, ax.index)} <${ax.kind}> Einheit kann zu undefined/null kollabieren (Achse ohne Einheit)`)
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
console.log(
  sizeViolations.length === 0
    ? `check:achsen — alle Achsen mit 10-px-Tick (keine Größen-Drift)`
    : `check:achsen — ${sizeViolations.length} Achse(n) OHNE 10-px-Tick`,
)
console.log(
  dropViolations.length === 0
    ? `check:achsen — keine Einheit kann zu undefined kollabieren`
    : `check:achsen — ${dropViolations.length} Achse(n) mit kollabierbarer Einheit`,
)

if (violations.length > 0 || tickViolations.length > 0 || sizeViolations.length > 0 || dropViolations.length > 0) {
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
  if (sizeViolations.length > 0) {
    console.error(`\n❌ ${sizeViolations.length} Achse(n) ohne 10-px-Tick (Größen-Drift, detLAN #29/#39):`)
    for (const v of sizeViolations) console.error('  · ' + v)
    console.error(
      '\nFix: `{...yAchse(schmal)}`/`{...xAchse(schmal)}` spreaden ODER `tick={ACHSEN_TICK}` ' +
        '(bzw. `tick={{ fontSize: 10 }}`) ergänzen. Custom-Renderer `tick={(…) => …}` ist erlaubt.',
    )
  }
  if (dropViolations.length > 0) {
    console.error(`\n❌ ${dropViolations.length} Achse(n) mit kollabierbarer Einheit (Achse ohne Einheit):`)
    for (const v of dropViolations) console.error('  · ' + v)
    console.error(
      '\nFix: Einheit immer setzen — `label={achsenEinheit(einheit || \'kW\')}` statt ' +
        '`label={einheit ? achsenEinheit(einheit) : undefined}` (kein Label-Drop).',
    )
  }
  process.exit(1)
}

console.log('✅ Alle Achsen: genau eine Einheit (nie kollabierbar) + de-DE tickFormatter + 10-px-Tick.')
