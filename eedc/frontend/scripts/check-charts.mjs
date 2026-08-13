#!/usr/bin/env node
/**
 * check-charts.mjs — Chart-SoT-Gate (B7 / D17-6, 2026-07-09).
 *
 * Die Gernot-Audit-Lehre codifiziert: R3b prüfte nur Farben/Badges/Tooltips, NICHT
 * die Chart-Komposition — „drei Torten, dreimal anders" konnte kein Wächter fangen
 * (kein Regel-Träger). Dieser Check gießt die STATISCH grep-baren Chart-Regeln:
 *
 *   R1 — Pie-SoT-Pflicht: Anteils-/Verteilungs-Charts laufen über die EINE SoT
 *        `components/ui/AnteilDonut` (Donut, B7 „Anteil → Donut"). Ein rohes
 *        `<PieChart>` woanders = Hand-Pie = Verstoß. Allowlist: die V3-only-IST-
 *        Seiten (nicht V4-route-erreichbar) bis zu ihren V3→V4-Paketen.
 *   R2 — Legenden-Bildsprache: jede Recharts-`<Legend>` MUSS `content={<ChartLegende`
 *        tragen (S1: Swatch + monochromer Text; roher `<Legend>` färbt die Schrift
 *        ein → „unseriös", detLAN/Rainer). Ein `<Legend>` ohne `ChartLegende` = Verstoß.
 *   R3 — Y-Achsen-Breite aus der Zentrale (D18-3, detlan #210): jede `<YAxis>` in
 *        src/v4 + src/components trägt ihre Breite explizit — `{...yAchse(…)}`
 *        (Default `ACHSEN_Y_BREITE` aus lib/chartAchse) oder hartes `width=`
 *        (Kategorie-Achsen horizontaler Balken). Der Recharts-Default 60 px ist
 *        verboten (verschwendeter Seitenrand; genau die Lücke, mit der D17-3/D17-5
 *        zweimal falsch „erledigt" gemeldet wurden). V3-Seiten (src/pages) ziehen
 *        mit Donor→V4 nach.
 *
 * BEWUSSTER BLIND SPOT (ehrlich benannt, [[feedback_verifiziert_nur_was_check_abdeckt]]):
 * die **Legende-Pflicht bei Multi-Serie** und **Label-Overflow** sind STATISCH nicht
 * verlässlich — Serien entstehen oft via `.map()` aus EINEM `<Bar>`-Literal (statisch
 * „1 Serie"), und Überlauf ist reine Render-Geometrie. Beides prüft das LAUFZEIT-Gate
 * `scripts/chart-audit.mjs` (Chromium) gegen das gerenderte DOM.
 *
 * Scope: app-weit (alle src/**.tsx außer Tests). Muster: check-achsen/check-chart-tooltip.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SRC = join(ROOT, 'src')

/** Die EINE Pie-SoT-Datei (definiert das erlaubte `<PieChart>`). */
const SOT_DATEI = 'src/components/ui/AnteilDonut.tsx'

/**
 * R1-Allowlist: **leer seit dem V3-Aufräumen 2026-08-13.**
 *
 * Sie trug sieben V3-only-Seiten mit Hand-Pie (`AktuellerMonat`, die sechs
 * `*Dashboard`-Seiten), die mit dem IA-V4-Flip (v4.0.0) ihre Route verloren hatten.
 * Deren Dateien sind mit dem Aufräumen gefallen — die Einträge zeigten seither ins
 * Leere und hätten eine gleichnamige neue Datei stumm freigestellt.
 * Neue Ausnahmen kommen nur mit Begründung dazu.
 */
const PIE_ALLOWLIST = new Set([])

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
 * Text des öffnenden Tags ab `start` (auf '<') bis zum '>' auf Klammertiefe 0.
 * Zählt `{}`-Tiefe (damit `content={<ChartLegende />}` NICHT als Tag-Ende gilt) und
 * überspringt '=>' (Arrow-Funktionen in Props). Muster aus check-achsen.mjs.
 */
function openTag(src, start) {
  let depth = 0
  for (let i = start + 1; i < src.length; i++) {
    const c = src[i]
    if (c === '{') depth++
    else if (c === '}') depth--
    else if (c === '>' && depth === 0) {
      if (src[i - 1] === '=') continue
      return src.slice(start, i + 1)
    }
  }
  return src.slice(start)
}

/** R3-Scope: V4 + der von V4 konsumierte geteilte Komponenten-Raum. */
const R3_SCOPE = ['src/v4/', 'src/components/']

const fehler = []
let pieOk = 0
let legendOk = 0
let yBreiteOk = 0

for (const file of tsxFiles(SRC)) {
  const rel = relative(ROOT, file).replaceAll('\\', '/')
  const src = readFileSync(file, 'utf8')
  const zeilen = src.split('\n')
  const zeileVon = (idx) => src.slice(0, idx).split('\n').length
  // Kommentarzeile (JSDoc `*`, `//`, JSX `{/*`) → Treffer darin ist Prosa, kein Tag.
  const istKommentar = (idx) => /^\s*(\*|\/\/|\{?\/\*|\*\/)/.test(zeilen[zeileVon(idx) - 1] ?? '')

  // ── R1: rohes <PieChart> nur in der SoT-Datei; sonst Allowlist-pflichtig ──────
  const pieRe = /<PieChart\b/g
  let pm
  while ((pm = pieRe.exec(src)) !== null) {
    if (istKommentar(pm.index)) continue
    if (rel === SOT_DATEI) { pieOk++; continue }
    if (PIE_ALLOWLIST.has(rel)) { pieOk++; continue }
    fehler.push(`✗ ${rel}:${zeileVon(pm.index)} — Hand-Pie <PieChart> — R1: Anteils-Charts über <AnteilDonut> (B7 „Anteil → Donut").`)
  }

  // ── R2: jede <Legend> trägt content={<ChartLegende … ──────────────────────────
  // (Tag mehrzeilig; `<ChartLegende` darf hinter einem JS-Kommentar im content stehen.)
  const legRe = /<Legend\b/g
  let lm
  while ((lm = legRe.exec(src)) !== null) {
    if (istKommentar(lm.index)) continue
    const tag = openTag(src, lm.index)
    if (/<ChartLegende\b/.test(tag)) { legendOk++; continue }
    fehler.push(`✗ ${rel}:${zeileVon(lm.index)} — rohe <Legend> — R2: content={<ChartLegende />} (S1-Bildsprache, kein farbiger Legendentext).`)
  }

  // ── R3: <YAxis> mit expliziter Breite — yAchse(…) (Zentrale) oder width= ──────
  if (R3_SCOPE.some((p) => rel.startsWith(p))) {
    const yRe = /<YAxis\b/g
    let ym
    while ((ym = yRe.exec(src)) !== null) {
      if (istKommentar(ym.index)) continue
      const tag = openTag(src, ym.index)
      if (/yAchse\(/.test(tag) || /\bwidth=/.test(tag)) { yBreiteOk++; continue }
      fehler.push(`✗ ${rel}:${zeileVon(ym.index)} — <YAxis> ohne Breite — R3: {...yAchse(schmal[, Breite])} aus lib/chartAchse oder explizites width= (kein Recharts-Default 60).`)
    }
  }
}

if (fehler.length) {
  console.error(fehler.join('\n'))
  console.error(`\ncheck:charts — ${fehler.length} Verstoß/Verstöße. (Laufzeit-Komposition: npm run check:chart-audit)`)
  process.exit(1)
}
console.log(`✅ check:charts — ${pieOk} Pie-Charts SoT/allowlist-konform, ${legendOk} Legenden über ChartLegende, ${yBreiteOk} Y-Achsen mit expliziter Breite (R3). (Multi-Serie-Legende + Overflow: check:chart-audit)`)
