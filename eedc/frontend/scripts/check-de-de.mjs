#!/usr/bin/env node
/**
 * check-de-de.mjs — de-DE-Anzeige-Garantie (R1, detLAN-Gegencheck).
 *
 * Findet **roh formatierte Zahl-/Datums-Anzeigen**, die NICHT durch die de-DE-Helfer
 * laufen (Tausenderpunkt fehlt → „1911" statt „1.911"; Dezimalpunkt statt Komma →
 * „98.7" statt „98,7"; locale-loses toLocale* nutzt die Laufzeit-Locale statt de-DE).
 *
 * Geflaggt wird (je Zeile; Ausnahme via Inline-Kommentar `de-de-allow: <Grund>`):
 *  A) `${ … Math.round(…)/…toFixed(…) … } <Einheit>` — Wert+Einheit ohne fmtZahl/fmtCalc.
 *  B) JSX-Textknoten `>{ … Math.round(…)/…toFixed(…) }<` — sichtbare rohe Zahl.
 *  C) `toLocaleString()` / `toLocaleDateString()` / `toLocaleTimeString()` OHNE Argument
 *     (kein `'de-DE'`) — Locale nicht erzwungen.
 *
 * Fix: de-DE-Helfer nutzen — Zahlen `fmtZahl(v, nk)` / `fmtCalc(v, nk)`; Datum/Zeit
 * `toLocaleDateString('de-DE', …)` bzw. `toLocaleTimeString('de-DE')`.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SRC = join(ROOT, 'src')
const EINHEIT = String.raw`(?:kWh|kW|MWh|GWh|Wh|€|km|%|t|kg|ct|kWp|Zyklen|Bäume|Starts|°C|h)`

function files(dir) {
  const out = []
  for (const n of readdirSync(dir)) {
    const p = join(dir, n)
    const s = statSync(p)
    if (s.isDirectory()) out.push(...files(p))
    else if ((n.endsWith('.tsx') || n.endsWith('.ts')) && !n.includes('.test.')) out.push(p)
  }
  return out
}

const reUnit = new RegExp(String.raw`\$\{[^}]*(?:Math\.round\(|\.toFixed\()[^}]*\}\s*` + EINHEIT)
const reJsxText = /[>]\{[^}]*(?:Math\.round\(|\.toFixed\()[^}]*\}\s*</
const reLocale = /\.toLocale(?:String|DateString|TimeString)\(\s*\)/
// „% mit Leerzeichen"-Regel (D9-B): ein JSX-Ausdruck `}` direkt gefolgt vom
// Prozent-Literal `%` ohne Leerzeichen → „… %" einsetzen. CSS-Prozent-Werte
// (`width={`${x}%`}`, `style={{left:`${x}%`}}`) stehen in Template-Strings → das
// `}%` ist dort von Backtick/Quote/`]` gefolgt und wird ausgeschlossen.
const reProzentEng = /\}%(?![`'"\])])/
// Rohe ISO-Datums-ANZEIGE: ein `*datum`-Feld in Anzeige-Position (wert:/JSX-{}/Template)
// OHNE de-DE-Formatter. Form-Inputs/State/Typdefs/interne Keys ausgeschlossen.
const reDatumAnzeige = /(?:wert:\s*|>\s*\{\s*|\$\{\s*)[\w.?![\]]*datum\b/i
const datumErlaubt = /formatDatum|langesDatum|toLocaleDateString|\.split|\.slice|value=|name=|type=|onChange|onUpdate|useState|defaultValue|placeholder|formData|gueltig_ab|interface |: ?string|\?:|=> ?\{?$|const \w+ ?=|let \w+ ?=/

// Scharf-Scope (Gernot 2026-06-28): v4-Oberfläche + geteilte Komponenten. Reine
// IST-v3-Seiten (src/pages/*, in v4 nicht sichtbar) = separater Nachzug → nur gezählt.
//
// ABER (detLAN-Gegencheck 6, 2026-06-28): v4-Sichten ziehen einzelne `pages/`-
// Komponenten ein (z. B. `PrognoseTabelle` aus `pages/auswertung/EnergieprofilPrognose`
// in der Aussicht). Die sind in V4 SICHTBAR → müssen mitgeprüft werden. Lösung:
// Import-Graph — Scope = v4/ + components/ + transitive Hülle der von dort
// importierten `pages/`-Dateien (nur pages→pages-Kanten verfolgt, damit lib/api/hooks
// NICHT in den Scharf-Scope rutschen). So fängt der Check jede künftig in v4
// eingezogene pages-Komponente automatisch.
function resolveImport(fromFile, spec) {
  if (!spec.startsWith('.')) return null
  const base = resolve(dirname(fromFile), spec)
  for (const cand of [base + '.tsx', base + '.ts', join(base, 'index.tsx'), join(base, 'index.ts')]) {
    try { if (statSync(cand).isFile()) return cand } catch { /* weiter */ }
  }
  return null
}
function pagesImportsOf(file) {
  const txt = readFileSync(file, 'utf8')
  return [...txt.matchAll(/from\s+'([^']+)'/g)]
    .map((m) => resolveImport(file, m[1]))
    .filter((p) => p && relative(ROOT, p).startsWith('src/pages/'))
}
const ALL = files(SRC)
const pagesInScope = new Set()
const queue = []
for (const f of ALL) {
  const rel = relative(ROOT, f)
  if (!rel.startsWith('src/v4/') && !rel.startsWith('src/components/')) continue
  for (const p of pagesImportsOf(f)) if (!pagesInScope.has(p)) { pagesInScope.add(p); queue.push(p) }
}
while (queue.length) {
  for (const p of pagesImportsOf(queue.shift())) if (!pagesInScope.has(p)) { pagesInScope.add(p); queue.push(p) }
}
const inScope = (rel, abs) => rel.startsWith('src/v4/') || rel.startsWith('src/components/') || pagesInScope.has(abs)

const hits = []
let pagesPending = 0
for (const f of ALL) {
  const rel = relative(ROOT, f)
  const lines = readFileSync(f, 'utf8').split('\n')
  lines.forEach((line, i) => {
    if (/de-de-allow:/.test(line)) return
    let grund = null
    if (/\.toFixed\(/.test(line)) grund = 'rohe .toFixed()-Anzeige (fmtZahl/fmtCalc nutzen)'
    else if (reUnit.test(line)) grund = 'Zahl+Einheit ohne de-DE (fmtZahl/fmtCalc)'
    else if (reJsxText.test(line)) grund = 'rohe Zahl im JSX-Text'
    else if (reLocale.test(line)) grund = 'toLocale* ohne \'de-DE\''
    else if (reProzentEng.test(line)) grund = '% direkt an der Zahl (Leerzeichen fehlt: „… %")'
    else if (reDatumAnzeige.test(line) && !datumErlaubt.test(line)) grund = 'rohes ISO-Datum in Anzeige (formatDatum nutzen)'
    if (!grund) return
    if (inScope(rel, f)) hits.push(`${rel}:${i + 1}  ${grund}\n      ${line.trim().slice(0, 110)}`)
    else pagesPending++
  })
}

console.log(`check:de-de — ${hits.length} roh formatierte Anzeige(n) in v4/+components/ (Soll: 0) · ${pagesPending} offen in IST-v3 pages/ (separater Nachzug)`)
if (hits.length) {
  console.error('\n❌ Nicht-de-DE-Anzeigen (Tausenderpunkt/Komma/Locale):')
  for (const h of hits) console.error('  · ' + h)
  console.error('\nFix: Zahlen → fmtZahl(v, nk)/fmtCalc(v, nk); Datum/Zeit → toLocale…(\'de-DE\', …). Bewusste Ausnahme: `/* de-de-allow: <Grund> */` in die Zeile.')
  process.exit(1)
}
console.log('✅ Alle geprüften Anzeigen sind de-DE-formatiert.')
