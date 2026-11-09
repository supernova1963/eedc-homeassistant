#!/usr/bin/env node
/**
 * check-dateilaenge.mjs — Wächter «Dateilänge» im Client (Päckchen CC Nachlauf N3, 9.11.2026; Backend-Schwester
 * `backend/tests/test_dateilaenge.py`).
 *
 * **Die Regel (Entscheid Gernot 9.11.2026 spät, Datei-Kriterium des Refactoring-Werkzeugs: 900 netto):**
 *  (1) keine neue Datei über 900 netto-Codezeilen — aufteilen (Schwesterdatei, Muster `*Teile.tsx`);
 *  (2) eine Datei der Baseline wächst höchstens auf `Baseline-Wert × 1,02` (Annahme: Fixes dürfen eine große Datei ein
 *      paar Zeilen verlängern; ein Umbau schreibt die Baseline neu, der Diff zeigt die Richtung);
 *  (3) ein verwaister Eintrag (Datei unter 900 oder weg) ist rot — die Baseline schrumpft nur.
 *
 * **Maß: netto-Codezeilen** = Zeilen mit mindestens einem Zeichen außerhalb von Kommentaren (ohne Leerzeile, ohne reine
 * Kommentarzeile, ohne JSDoc-Block) — die Fassung von `komplexitaet.py::netto` für TypeScript: dort fallen Kommentar und
 * Docstring weg, hier Kommentar und JSDoc (TypeScript kennt keine Docstrings; ein mehrzeiliges Template-Literal zählt als
 * Code). Kommentare erkennt der TypeScript-Parser (`forEachLeadingCommentRange` vor jedem Token), nicht ein Muster.
 * Prüfmenge: `src/**\/*.ts|tsx` ohne `*.test.*`.
 *
 * **Baseline `dateilaenge-baseline.txt`** (Format `netto<TAB>pfad relativ zu src/`), neu schreiben nach einem Umbau:
 *
 *   cd eedc/frontend && node scripts/check-dateilaenge.mjs --baseline
 *
 * `--liste` zeigt alle Dateien über 600 netto.
 */
import { readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const argv = process.argv.slice(2)
const FE = join(dirname(fileURLToPath(import.meta.url)), '..')
const SRC = join(FE, 'src')
const BASELINE = join(FE, 'dateilaenge-baseline.txt')
const ts = createRequire(join(FE, 'package.json'))('typescript')

const SCHWELLE = 900
const TOLERANZ = 1.02

function walkFiles(dir, out = []) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name)
    if (e.isDirectory()) walkFiles(p, out)
    else if (/\.(ts|tsx)$/.test(e.name) && !/\.test\.(ts|tsx)$/.test(e.name)) out.push(p)
  }
  return out
}

/** Netto-Codezeilen: Zeilen, die außerhalb von Kommentaren ein Nicht-Leerzeichen tragen. */
export function netto(text, dateiname = 'x.tsx') {
  const sf = ts.createSourceFile(dateiname, text, ts.ScriptTarget.Latest, true,
    dateiname.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
  const kommentar = new Uint8Array(text.length)
  const markiere = (pos, end) => { for (let i = pos; i < end; i++) kommentar[i] = 1 }
  const besuche = (node) => {
    const kinder = node.getChildren(sf)
    if (kinder.length === 0) {
      ts.forEachLeadingCommentRange(text, node.pos, (pos, end) => markiere(pos, end))
      return
    }
    for (const k of kinder) besuche(k)
  }
  besuche(sf)
  // Kommentare hinter dem letzten Token (Leading-Trivia des Dateiendes).
  ts.forEachLeadingCommentRange(text, sf.endOfFileToken.pos, (pos, end) => markiere(pos, end))
  let zeilen = 0
  let code = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (c === '\n') { if (code) zeilen++; code = false; continue }
    if (!kommentar[i] && c !== ' ' && c !== '\t' && c !== '\r') code = true
  }
  if (code) zeilen++
  return zeilen
}

function messen() {
  const werte = new Map()
  for (const p of walkFiles(SRC)) werte.set(relative(SRC, p).split('\\').join('/'), netto(readFileSync(p, 'utf8'), p))
  return werte
}

function baselineLesen() {
  const out = new Map()
  for (const z of readFileSync(BASELINE, 'utf8').split('\n')) {
    if (!z.trim() || z.startsWith('#')) continue
    const [wert, datei] = z.split('\t')
    out.set(datei, Number(wert))
  }
  return out
}

const werte = messen()
if (argv.includes('--baseline')) {
  const zeilen = [...werte].filter(([, v]) => v > SCHWELLE).sort(([a], [b]) => (a < b ? -1 : 1)).map(([k, v]) => `${v}\t${k}`)
  writeFileSync(BASELINE,
    `# Bestand der Client-Dateien mit mehr als ${SCHWELLE} netto-Codezeilen — darf nur schrumpfen.\n` +
    '# Neu schreiben: cd eedc/frontend && node scripts/check-dateilaenge.mjs --baseline. Format: netto<TAB>pfad (relativ zu src/)\n' +
    zeilen.join('\n') + '\n')
  console.log(`${zeilen.length} Dateien > ${SCHWELLE} netto nach dateilaenge-baseline.txt geschrieben`)
  process.exit(0)
}
if (argv.includes('--liste')) {
  for (const [k, v] of [...werte].filter(([, v]) => v > 600).sort((a, b) => b[1] - a[1])) console.log(`${v}\t${k}`)
  process.exit(0)
}
const baseline = baselineLesen()
const neu = [...werte].filter(([k, v]) => v > SCHWELLE && !baseline.has(k))
const gewachsen = [...baseline].filter(([k, alt]) => (werte.get(k) ?? 0) > alt * TOLERANZ)
const verwaist = [...baseline].filter(([k]) => (werte.get(k) ?? 0) <= SCHWELLE)
let rot = false
if (neu.length) {
  rot = true
  console.error(`check:dateilaenge — ${neu.length} neue Datei(en) über ${SCHWELLE} netto-Codezeilen — aufteilen ` +
    '(Schwesterdatei), nicht eintragen:\n  ' + neu.map(([k, v]) => `${v}\t${k}`).join('\n  '))
}
if (gewachsen.length) {
  rot = true
  console.error(`check:dateilaenge — ${gewachsen.length} Datei(en) über Baseline × ${TOLERANZ} gewachsen — aufteilen, ` +
    'die Baseline wird nicht hochgesetzt:\n  ' + gewachsen.map(([k, alt]) => `${alt} → ${werte.get(k)}\t${k}`).join('\n  '))
}
if (verwaist.length) {
  rot = true
  console.error(`check:dateilaenge — ${verwaist.length} Baseline-Eintrag/-Einträge liegen jetzt ≤ ${SCHWELLE} oder fehlen — ` +
    'die Baseline schrumpft im Commit (`node scripts/check-dateilaenge.mjs --baseline`):\n  ' +
    verwaist.map(([k, alt]) => `${alt} → ${werte.get(k) ?? '—'}\t${k}`).join('\n  '))
}
if (rot) process.exit(1)
console.log(`check:dateilaenge — ${werte.size} Dateien, ${baseline.size} über ${SCHWELLE} (alle in der Baseline)`)
