#!/usr/bin/env node
/**
 * check-rechenstellen.mjs — Wächter «Rechenstellen» im Client (Päckchen Z3, 9.11.2026; Backend-Schwester
 * `backend/tests/test_dezentrale_rechenstellen.py`).
 *
 * **Die Regel (ADR-001 «eine Formel, ein Ort»; CLAUDE.md «der Client rechnet nichts»):** in Sichten
 * (`components/`, `pages/`, `v4/`) und Hooks entsteht kein neuer Rechenausdruck der Gestalten Quote zweier Mengen
 * (`E/E`), Differenz zweier Mengen (`E-E`), Menge × Preis (`E*G`), Menge × Zahl-Literal (`E*L`), Menge ÷ Leistung
 * (`E/P`, spezifischer Ertrag) und Preis ÷ Menge (`G/E`) — außer als Einheitenumrechnung (× 100, ÷ 1000 …) oder
 * Rundung (`Math.round(x × 10) / 10`); Geometrie, Datum, Text und Zähler zählen gar nicht erst. Die Größe kommt als
 * Feld aus dem Backend (Layer `core/berechnungen/`).
 *
 * Kern der Erhebung «dezentrale Berechnungen» (TypeScript-Compiler-API, nur lesend): Rollen nach dem Operandennamen
 * (E Energie · G Geld · P Leistung · Q Quote · C CO₂ · T Zeit · S sonst · L Literal). Schlüssel ohne Zeilennummer:
 * `datei::funktion::operator::operanden-ohne-leerzeichen`, Multimenge.
 *
 * **Baseline `rechenstellen-baseline.txt`, darf nur schrumpfen** (Stand nach Päckchen Z2; darin die Kandidaten des
 * Auftrags «Z-Client»). Rot bei einer neuen Stelle **und** bei einem verwaisten Eintrag — eine Stelle, die ins
 * Backend zieht, wird aus der Baseline gestrichen, damit die Zahl im Commit sinkt:
 *
 *   cd eedc/frontend && node scripts/check-rechenstellen.mjs --baseline
 *
 * `--liste` zeigt die geführten Stellen mit Datei:Zeile.
 */
import { readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const argv = process.argv.slice(2)
const FE = join(dirname(fileURLToPath(import.meta.url)), '..')
const SRC = join(FE, 'src')
const BASELINE = join(FE, 'rechenstellen-baseline.txt')
const ts = createRequire(join(FE, 'package.json'))('typescript')

const GESTALTEN = new Set(['E/E', 'E-E', 'E*G', 'E*L', 'E/P', 'G/E'])
const KLASSEN = new Set(['sicht', 'hooks'])
const OHNE_MARKER = ['einheit', 'rundung']

const FACH = new RegExp(
  'kwh|wh|euro|cent|ct|kg|prozent|anteil|preis|kosten|ersparnis|erloes|verguetung|co2|ertrag|leistung|kw\\b|kwp|faktor|wirkungsgrad|effizienz|cop|jaz|az\\b|ladung|entladung|' +
  'verbrauch|erzeugung|einspeisung|netzbezug|bezug|soc|kapazitaet|km|liter|gas|waerme|temperatur|grad|strahlung|ghi|gti|degradation|amortisation|roi|rendite|zins|' +
  'abschreibung|steuer|ust|mwst|bilanz|autarkie|eigenverbrauch|peak|spitze|mittel|summe|saldo|tarif|grundgebuehr|_kwh|_euro|_kg|_prozent|_cent|_km|ersparnis|anteil|preis|kosten|ertrag')
const GEOM = /^(width|height|x|y|cx|cy|r|px|offset|index|idx|i|len|length|count|anzahl|rows|cols|size|zoom|scale|pad|gap|margin|radius)$/i
const DATUM = /getTime|new Date|Date\.|\bDate\(|getFullYear|getMonth|getDate|getHours/
const EINHEITEN = new Set([100, 1000, 1e6, 12, 24, 60, 3600, 365, 365.25, 7, 30, 31, 0.001, 0.01])
const KTOKEN = /\bN-\d|\bF-\d|\bP\d+\b|\bADR|check:/
const OPS = new Map([
  [ts.SyntaxKind.AsteriskToken, '*'], [ts.SyntaxKind.SlashToken, '/'], [ts.SyntaxKind.PercentToken, '%'],
  [ts.SyntaxKind.PlusToken, '+'], [ts.SyntaxKind.MinusToken, '-'],
  [ts.SyntaxKind.PlusEqualsToken, '+='], [ts.SyntaxKind.MinusEqualsToken, '-='],
  [ts.SyntaxKind.AsteriskEqualsToken, '*='], [ts.SyntaxKind.SlashEqualsToken, '/='],
])
const ROUNDFN = new Set(['round', 'floor', 'ceil', 'trunc'])
const ROLLEN = [
  ['E', /kwh|wh\b|mwh|erzeugung|verbrauch|einspeisung|netzbezug|bezug|ladung|entladung|eigenverbrauch|menge|ertrag(?!.*(euro|cent))/],
  ['G', /euro|cent|\bct\b|preis|kosten|ersparnis|erloes|verguetung|tarif|grundgebuehr|betrag|zins|abschreibung|steuer|ust|mwst|rendite/],
  ['P', /\bkw\b|kwp|\bw\b|leistung|peak|spitze/],
  ['Q', /prozent|anteil|quote|faktor|wirkungsgrad|effizienz|cop|jaz|\baz\b|autarkie|degradation|verlust/],
  ['C', /co2|\bkg\b/],
  ['T', /stunden|minuten|sekunden|tage\b|\bh\b|dauer|zeit/],
]
const REIHE = 'EGPQCTSL'
function rolleName(name) {
  const s = name.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/_/g, ' ').toLowerCase().trim()
  for (const [r, rx] of ROLLEN) if (rx.test(s)) return r
  return 'S'
}
function gestaltVon(rl, rr, op) {
  const basis = op.length > 1 && op.endsWith('=') ? op.slice(0, -1) : op
  const aug = basis !== op
  if ((basis === '*' || basis === '+') && !aug && REIHE.indexOf(rl) > REIHE.indexOf(rr)) [rl, rr] = [rr, rl]
  return rl + basis + rr
}
const norm = (s) => s.replace(/\s+/g, ' ').trim()
const kuerze = (s, n = 80) => { s = norm(s); return s.length <= n ? s : s.slice(0, n - 1) + '…' }

function walkFiles(dir, out = []) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name)
    if (e.isDirectory()) walkFiles(p, out)
    else if (/\.(ts|tsx)$/.test(e.name)) out.push(p)
  }
  return out
}
const alle = walkFiles(SRC).sort()
function ausgeschlossen(rel) {
  return /\.test\.(ts|tsx)$/.test(rel) || rel.startsWith('test/') || /^api\/[^/]*demo[^/]*$/i.test(rel) ||
    rel === 'lib/colors.ts' || /^lib\/format[^/]*$/.test(rel)
}
function klasse(rel) {
  if (/^(components|pages|v4)\//.test(rel)) return 'sicht'
  if (rel.startsWith('lib/')) return 'lib'
  if (rel.startsWith('api/')) return 'api'
  if (rel.startsWith('hooks/')) return 'hooks'
  return 'sonst'
}

const unwrap = (n) => {
  for (;;) {
    if (ts.isParenthesizedExpression(n) || ts.isNonNullExpression(n) || ts.isAsExpression(n) || ts.isTypeAssertionExpression?.(n) || (ts.isSatisfiesExpression?.(n))) n = n.expression
    else if (ts.isBinaryExpression(n) && (n.operatorToken.kind === ts.SyntaxKind.QuestionQuestionToken || n.operatorToken.kind === ts.SyntaxKind.BarBarToken) && litwert(n.right) !== null) n = n.left
    else return n
  }
}
function litwert(n) {
  if (ts.isNumericLiteral(n)) return Number(n.text.replace(/_/g, ''))
  if (ts.isParenthesizedExpression(n)) return litwert(n.expression)
  if (ts.isPrefixUnaryExpression(n) && (n.operator === ts.SyntaxKind.MinusToken || n.operator === ts.SyntaxKind.PlusToken)) {
    const v = litwert(n.operand); return v === null ? null : (n.operator === ts.SyntaxKind.MinusToken ? -v : v)
  }
  if (ts.isBinaryExpression(n) && OPS.has(n.operatorToken.kind) && !'+=,-=,*=,/='.split(',').includes(OPS.get(n.operatorToken.kind))) {
    const a = litwert(n.left), b = litwert(n.right); if (a === null || b === null) return null
    switch (OPS.get(n.operatorToken.kind)) { case '*': return a * b; case '/': return a / b; case '%': return a % b; case '+': return a + b; case '-': return a - b }
  }
  return null
}
const istText = (n) => { n = n.kind === ts.SyntaxKind.ParenthesizedExpression ? n.expression : n; return ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) || ts.isTemplateExpression(n) }
function ident(n0) {
  const n = unwrap(n0)
  if (ts.isIdentifier(n)) return [n.text, 'name']
  if (ts.isPropertyAccessExpression(n)) return [n.name.text, 'attr']
  if (ts.isElementAccessExpression(n) && n.argumentExpression && ts.isStringLiteralLike(n.argumentExpression)) return [n.argumentExpression.text, 'key']
  return null
}
function alleIdents(n, acc = []) {
  if (ts.isIdentifier(n)) acc.push(n.text)
  else if (ts.isStringLiteralLike(n)) acc.push(n.text)
  ts.forEachChild(n, (c) => alleIdents(c, acc))
  return acc
}

function kommentarZeilen(sf, text) {
  const map = new Map(); const seen = new Set()
  const add = (r) => {
    if (seen.has(r.pos)) return; seen.add(r.pos)
    const t = text.slice(r.pos, r.end)
    const l0 = sf.getLineAndCharacterOfPosition(r.pos).line + 1, l1 = sf.getLineAndCharacterOfPosition(r.end).line + 1
    for (let l = l0; l <= l1; l++) map.set(l, (map.get(l) || '') + ' ' + t)
  }
  const visit = (n) => {
    const fs = n.getFullStart()
    ;(ts.getLeadingCommentRanges(text, fs) || []).forEach(add)
    ;(ts.getTrailingCommentRanges(text, n.getEnd()) || []).forEach(add)
    for (const c of n.getChildren(sf)) visit(c)
  }
  visit(sf)
  return map
}

function laufen() {
  const treffer = [], uebersprungen = [], fehler = []
  const skip = { zaehler: 0, geometrie: 0, geometrie_mit_fach: 0, datum: 0, text: 0, beide_literale: 0 }
  const dateien = []
  for (const p of alle) {
    const rel = relative(SRC, p).split('\\').join('/')
    if (ausgeschlossen(rel)) continue
    dateien.push([p, rel])
  }
  for (const [p, rel] of dateien) {
    let text
    try { text = readFileSync(p, 'utf8') } catch (e) { fehler.push({ datei: rel, fehler: String(e) }); continue }
    let sf
    try {
      sf = ts.createSourceFile(p, text, ts.ScriptTarget.Latest, true, p.endsWith('x') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
    } catch (e) { fehler.push({ datei: rel, fehler: String(e) }); continue }
    const synt = (sf.parseDiagnostics || []).length
    if (synt) fehler.push({ datei: rel, fehler: `${synt} Parse-Diagnosen (Datei trotzdem ausgewertet)` })
    const komm = kommentarZeilen(sf, text)
    const kl = klasse(rel)
    const kopf = text.split('\n').slice(0, 30).join('\n')
    const spiegel = kl === 'lib' && /Spiegel|SoT|N-252/.test(kopf)
    const line = (n) => sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1

    const funktionsName = (n) => {
      const names = []
      for (let p2 = n.parent; p2; p2 = p2.parent) {
        if (ts.isFunctionDeclaration(p2) && p2.name) names.push(p2.name.text)
        else if (ts.isMethodDeclaration(p2) || ts.isGetAccessor(p2) || ts.isSetAccessor(p2)) { if (p2.name) names.push(p2.name.getText(sf)) }
        else if (ts.isClassDeclaration(p2) && p2.name) names.push(p2.name.text)
        else if ((ts.isArrowFunction(p2) || ts.isFunctionExpression(p2))) {
          const par = p2.parent
          if (par && ts.isVariableDeclaration(par) && ts.isIdentifier(par.name)) names.push(par.name.text)
          else if (par && ts.isPropertyAssignment(par) && par.name) names.push(par.name.getText(sf))
        }
      }
      return names.length ? names.reverse().join('.') : '<modul>'
    }
    const inReduce = (n) => {
      for (let p2 = n.parent; p2; p2 = p2.parent) {
        if (ts.isCallExpression(p2) && ts.isPropertyAccessExpression(p2.expression) && p2.expression.name.text === 'reduce') return true
        if (ts.isFunctionDeclaration(p2)) return false
      }
      return false
    }
    const inSchleife = (n) => {
      for (let p2 = n.parent; p2; p2 = p2.parent) {
        if (ts.isForStatement(p2) || ts.isForOfStatement(p2) || ts.isForInStatement(p2) || ts.isWhileStatement(p2) || ts.isDoStatement(p2)) return true
        if (ts.isFunctionDeclaration(p2) || ts.isArrowFunction(p2) || ts.isFunctionExpression(p2) || ts.isMethodDeclaration(p2)) return false
      }
      return false
    }
    const rundungAussen = (n, op, links, rechts) => {
      if (op !== '/') return false
      const l = unwrap(links), r = litwert(rechts)
      if (r === null || ![10, 100, 1000, 10000].includes(r)) return false
      return ts.isCallExpression(l) && ts.isPropertyAccessExpression(l.expression) && ts.isIdentifier(l.expression.expression) &&
        l.expression.expression.text === 'Math' && ROUNDFN.has(l.expression.name.text)
    }
    const rundungInnen = (n, op, lit) => {
      if (op !== '*' || ![10, 100, 1000, 10000].includes(lit)) return false
      let p2 = n.parent
      while (p2 && ts.isParenthesizedExpression(p2)) p2 = p2.parent
      return p2 && ts.isCallExpression(p2) && ts.isPropertyAccessExpression(p2.expression) && ts.isIdentifier(p2.expression.expression) &&
        p2.expression.expression.text === 'Math' && ROUNDFN.has(p2.expression.name.text)
    }

    const visit = (n) => {
      if (ts.isBinaryExpression(n) && OPS.has(n.operatorToken.kind)) {
        const op = OPS.get(n.operatorToken.kind)
        const aug = op.length === 2
        const links = n.left, rechts = n.right
        const lv = litwert(links), rv = litwert(rechts)
        const tl = norm(links.getText(sf)), tr = norm(rechts.getText(sf))
        const meta = { datei: rel, zeile: line(n) }
        if (istText(unwrap(links)) || istText(unwrap(rechts))) skip.text++
        else if (lv !== null && rv !== null) skip.beide_literale++
        else {
          const il = ident(links), ir = ident(rechts)
          const fachNamen = [il, ir].filter((i) => i && FACH.test(i[0].toLowerCase().replace(/^_+/, ''))).map((i) => i[0])
          const a = fachNamen.length > 0, b = lv !== null || rv !== null
          const geom = [il, ir].some((i) => i && GEOM.test(i[0]))
          if (a || b) {
            const gesamt = tl + ' ' + tr
            const fachGesamt = alleIdents(links).concat(alleIdents(rechts)).some((s) => FACH.test(s.toLowerCase()))
            if ((op === '+' || op === '-' || op === '+=') && rv === 1 && lv === null) skip.zaehler++
            else if (geom && (a === false || (il && GEOM.test(il[0]) && !(ir && FACH.test(ir[0].toLowerCase()))) || (ir && GEOM.test(ir[0]) && !(il && FACH.test(il[0].toLowerCase()))))) { skip.geometrie++ }
            else if (geom) { skip.geometrie_mit_fach++; uebersprungen.push({ ...meta, grund: 'geometrie_mit_fach', operanden: [kuerze(tl), kuerze(tr)] }) }
            else if (DATUM.test(gesamt) && !fachGesamt) skip.datum++
            else {
              const lit = [lv, rv].filter((v) => v !== null)
              const marker = []
              let einh = lit.some((v) => EINHEITEN.has(v))
              const pc = (lv === null ? il : ir)
              if (pc && /(_prozent|_cent|prozent|cent)$/i.test(pc[0]) && lit.includes(100) && (op === '/' || op === '*' || op === '/=' || op === '*=')) einh = true
              if (einh) marker.push('einheit')
              if (rundungAussen(n, op, links, rechts) || (lv === null || rv === null) && lit.length === 1 && rundungInnen(n, op, lit[0])) marker.push('rundung')
              if (aug && (op === '+=' || op === '-=') && inSchleife(n) || inReduce(n) || /\.sum\b|\bsum\(/.test(gesamt)) marker.push('aggregation')
              if (spiegel) marker.push('spiegel')
              const zl = meta.zeile
              let kt = false
              for (let l = zl - 2; l <= zl + 2; l++) if (komm.has(l) && KTOKEN.test(komm.get(l))) { kt = true; break }
              if (kt) marker.push('kommentar-token')
              const rolleOp = (x, v) => (v !== null ? 'L' : (() => { const i = ident(x); return i ? rolleName(i[0]) : 'S' })())
              const rl = rolleOp(links, lv), rr = rolleOp(rechts, rv)
              treffer.push({
                rollen: [rl, rr], gestalt: gestaltVon(rl, rr, op),
                datei: rel, zeile: zl, funktion: funktionsName(n), klasse: kl, operator: op,
                operanden: [kuerze(tl), kuerze(tr)], operanden_voll: [norm(tl), norm(tr)],
                literale: lit, via: a ? [il, ir].find((i) => i && fachNamen.includes(i[0]))[1] : 'literal', marker,
              })
            }
          }
        }
      }
      ts.forEachChild(n, visit)
    }
    visit(sf)

  }
  treffer.sort((a, b) => a.datei.localeCompare(b.datei) || a.zeile - b.zeile)
  return { treffer, fehler }
}

const schluessel = (t) => `${t.datei}::${t.funktion}::${t.operator}::` + t.operanden_voll.map((o) => o.replace(/\s+/g, '')).join(',')
const gefuehrt = (t) => GESTALTEN.has(t.gestalt) && KLASSEN.has(t.klasse) && !t.marker.some((m) => OHNE_MARKER.includes(m))

function baselineLesen() {
  const m = new Map()
  for (const z of readFileSync(BASELINE, 'utf8').split('\n')) {
    if (!z.trim() || z.startsWith('#')) continue
    const k = z.split('\t')[0]
    m.set(k, (m.get(k) || 0) + 1)
  }
  return m
}

const { treffer, fehler } = laufen()
const stellen = treffer.filter(gefuehrt)
if (fehler.length) {
  console.error('check:rechenstellen — Dateien mit Parse-Fehlern (Prüfmenge unvollständig):\n  ' + fehler.map((f) => `${f.datei}: ${f.fehler}`).join('\n  '))
  process.exit(1)
}
if (argv.includes('--baseline')) {
  const zeilen = stellen.map((t) => `${schluessel(t)}\t${t.gestalt}`).sort()
  writeFileSync(BASELINE,
    '# Rechenstellen im Client (Gestalten E/E E-E E*G E*L E/P G/E, Sichten/Hooks, ohne einheit/rundung) — darf nur schrumpfen.\n' +
    '# Neu schreiben: cd eedc/frontend && node scripts/check-rechenstellen.mjs --baseline. Format: schluessel<TAB>gestalt\n' +
    zeilen.join('\n') + '\n')
  console.log(`${zeilen.length} Rechenstellen nach rechenstellen-baseline.txt geschrieben`)
  process.exit(0)
}
if (argv.includes('--liste')) {
  for (const t of stellen) console.log(`${t.datei}:${t.zeile}\t${t.gestalt}\t${t.operanden[0]} ${t.operator} ${t.operanden[1]}`)
  process.exit(0)
}
const baseline = baselineLesen()
const rest = new Map(baseline)
const neu = []
for (const t of stellen) {
  const k = schluessel(t)
  if ((rest.get(k) || 0) > 0) rest.set(k, rest.get(k) - 1)
  else neu.push(t)
}
const verwaist = [...rest].filter(([, n]) => n > 0).map(([k, n]) => (n > 1 ? `${k} (×${n})` : k))
let rot = false
if (neu.length) {
  rot = true
  console.error(`check:rechenstellen — ${neu.length} neue Rechenstelle(n) im Client:\n  ` +
    neu.map((t) => `${t.datei}:${t.zeile}  ${t.gestalt}  ${t.operanden[0]} ${t.operator} ${t.operanden[1]}`).join('\n  ') +
    '\nDie Größe als Feld aus dem Backend lesen (Formel im Layer `core/berechnungen/`) oder bewusst in die Baseline: ' +
    '`node scripts/check-rechenstellen.mjs --baseline`')
}
if (verwaist.length) {
  rot = true
  console.error(`check:rechenstellen — ${verwaist.length} Baseline-Eintrag/-Einträge ohne Rechenstelle — die Baseline ` +
    'schrumpft im Commit (`node scripts/check-rechenstellen.mjs --baseline`):\n  ' + verwaist.join('\n  '))
}
if (rot) process.exit(1)
console.log(`check:rechenstellen — ${stellen.length} Rechenstellen, alle in der Baseline`)
