#!/usr/bin/env node
/**
 * check-parkbar-vollstaendig.mjs — Vollständigkeits-Wächter der Element-Park-Doktrin
 * (Phase 1, Gernot 2026-07-09).
 *
 * Schwester von `check-parkbar.mjs`. Die zwei Hälften der Doktrin, zwei Wächter:
 *   • check:parkbar            → ATOMARITÄT  (jede <Parkbar> = genau EINE Anzeige;
 *                                Bündel-Tripwire über eine Allowlist der Kinder).
 *   • check:parkbar-vollstaendig → VOLLSTÄNDIGKEIT (JEDE Anzeige in einer Park-Sicht
 *                                IST parkbar; kein Chart/Tabelle/Balken ohne <Parkbar>).
 *
 * Warum: `check:parkbar` sieht eine FEHLENDE Parkbar prinzipiell nicht — er prüft nur
 * vorhandene. Genau da rutschten un-parkbare Anzeigen durch (CO₂-Block „Berechnungs-
 * grundlage" komplett parkbar-frei; Trailing-Hinweise). Dieser Wächter schließt die
 * Lücke, damit „jeder Block vollständig auflösbar" nicht per Handsweep, sondern
 * automatisch gilt (→ parkt man alle Elemente, verschwindet der Block; deckt zugleich
 * die „ganzer Block weg"-Anforderung ab, ohne eigenes Block-Park-Feature).
 *
 * Reichweite (bewusst): NUR park-fähige Orchestrierungs-Dateien (importieren `Parkbar`).
 * Die geteilten Einzel-Anzeige-Komponenten (`TagVerlaufChart`, `SpeicherVerlaufCharts`…)
 * importieren KEINE Parkbar → sie werden hier NICHT geprüft; ihre interne Entbündelung
 * ist Phase 2 (check:parkbar-Recursion). So bleibt Phase 1 additiv & rausch-arm.
 *
 * Mechanik:
 *   (A) Un-parkbares Anzeige-Primitiv: ein hoch-signal-Display-Tag (Recharts-Container,
 *       <table>, <dl>, VerteilungsBalken, KpiUnterblock, KPICard) das bei Parkbar-
 *       Verschachtelungstiefe 0 steht (also außerhalb jeder <Parkbar>). <KpiStrip> ist
 *       KEIN Verstoß — es parkt jede Kachel selbst.
 *   (B) Block ohne jede Parkbar: ein `render:`-Körper (BlockShell-Block) der WEDER
 *       <Parkbar> NOCH <KpiStrip> enthält, aber sichtbaren Inhalt (<p>/<dl>/<table>/
 *       Wert-Grid) rendert → der ganze Block ist un-auflösbar (CO₂-„Berechnungsgrundlage").
 *
 * Ehrliche Grenze: freistehende Hinweis-`<p>` NEBEN Parkbars (Trailing-Hinweis in einem
 * Block, der sonst Parkbars hat) erkennt (A)/(B) NICHT zuverlässig — `<p>` ist nicht von
 * Layout-Text unterscheidbar. Solche Reste bleiben ein Auge-Fall (in der Fixliste als
 * „soft" markiert, wenn heuristisch getroffen). Bewusste Ausnahmen → Allowlist.
 */
import { readdirSync, readFileSync, statSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SRC = join(ROOT, 'src')
const ALLOWLIST_PFAD = join(ROOT, 'scripts', 'parkbar-vollstaendig-allowlist.json')
const ALLOWLIST = new Set(existsSync(ALLOWLIST_PFAD) ? JSON.parse(readFileSync(ALLOWLIST_PFAD, 'utf8')) : [])

// Hoch-signal Anzeige-Primitive (unzweideutig „eine Anzeige"). Bewusst OHNE rohes
// <p>/<div> (nicht von Layout unterscheidbar) und OHNE <KpiStrip>/<KpiUnterblock>
// (self-parken je Kachel via `parkId`, B4 Gernot 2026-07-09 — wie KpiStrip).
const DISPLAY_MARKER = [
  'ResponsiveContainer', 'table', 'VerteilungsBalken', 'KPICard',
  'AreaChart', 'BarChart', 'LineChart', 'ComposedChart', 'RadarChart', 'PieChart',
]
// Ein Token-Regex, in Quell-Reihenfolge ausgewertet: Parkbar-Auf/Zu + Display-Marker.
const TOKEN = new RegExp(
  `(<Parkbar\\b)|(</Parkbar>)|<(${DISPLAY_MARKER.join('|')})\\b`, 'g',
)

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

const zeileVon = (src, idx) => src.slice(0, idx).split('\n').length

/** Balancierten `(...)`-Körper ab Position `open` (Index des `(`) zurückgeben. */
function balancierteKlammer(src, open) {
  let d = 0
  for (let i = open; i < src.length; i++) {
    if (src[i] === '(') d++
    else if (src[i] === ')') { d--; if (d === 0) return src.slice(open, i + 1) }
  }
  return src.slice(open)
}

/** Top-Level-Komponenten-/Funktions-Körper (Spalte 0). Jede Sicht/Komponente wird
 *  einzeln betrachtet: so trennt (A) „Sicht mit Parkbars + roher Anzeige" (PVGIS) von
 *  „atomare Anzeige-Komponente ohne Parkbar" (KurzfristDetails — die parkt der Aufrufer). */
function topLevelKoerper(src) {
  const grenzen = []
  const re = /^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+\w+|^(?:export\s+)?const\s+\w+\s*[:=]/gm
  let m
  while ((m = re.exec(src))) grenzen.push(m.index)
  const out = []
  for (let i = 0; i < grenzen.length; i++) {
    const start = grenzen[i]
    const ende = i + 1 < grenzen.length ? grenzen[i + 1] : src.length
    out.push({ start, body: src.slice(start, ende) })
  }
  return out
}

/** Alle `render: (...) => (`-Körper innerhalb eines Textstücks (mit Quell-Offset). */
function renderKoerper(text, base) {
  const out = []
  const re = /render:\s*\([^)]*\)\s*=>\s*\(/g
  let m
  while ((m = re.exec(text))) {
    const open = text.indexOf('(', m.index + m[0].length - 1)
    out.push({ offset: base + open, renderOffset: base + m.index, body: balancierteKlammer(text, open) })
  }
  return out
}

/** (A) Display-Marker bei Parkbar-Tiefe 0 = un-parkbare Anzeige. */
function findeUnparkbareMarker(body, baseOffset, src, rel) {
  const treffer = []
  let tiefe = 0
  let m
  TOKEN.lastIndex = 0
  while ((m = TOKEN.exec(body))) {
    if (m[1]) tiefe++
    else if (m[2]) tiefe = Math.max(0, tiefe - 1)
    else if (m[3] && tiefe === 0) {
      treffer.push({ datei: rel, zeile: zeileVon(src, baseOffset + m.index), kind: m[3], art: 'A' })
    }
  }
  return treffer
}

/** (B) render-Körper ohne jede <Parkbar>/<KpiStrip>, aber mit echtem Anzeige-Inhalt.
 *  Bewusst OHNE `<p>`: ein alleinstehendes `<p>` ist Leerzustand („keine Daten") oder
 *  Delegations-Fallback — nichts zu parken. Echte Anzeige = Tabelle/Liste/Wert-Grid. */
function istUnparkbarerBlock(body) {
  const hatPark = /<Parkbar\b/.test(body) || /<KpiStrip\b/.test(body)
  const hatAnzeige = /<(dl|table|ul|ol)\b/.test(body) || /className="[^"]*grid/.test(body)
  return !hatPark && hatAnzeige
}

// Mechanik-Dateien: parken selbst je Element (KpiStrip → je Kachel, FormBlock → je Feld)
// → ihr Display-Marker bei Tiefe 0 (die `card`-Variable vor der Umhüllung) ist kein Bug.
const MECHANIK = ['src/components/blocks/KpiStrip.tsx', 'src/components/blocks/FormBlock.tsx']

// Ausgeklammert (Gernot 2026-07-09): Einstellungen (kohäsive Konfig-Sektionen = EINE
// Anzeige, kein Park-Ziel) und Cockpit/Live (Gernot-Stopp, nicht anfassen).
const AUSSER_REICHWEITE = (rel) =>
  /instellungen|Settings/.test(rel) || /CockpitLive|\/live\//.test(rel)

const verstoesse = []
let geprueft = 0

for (const f of files(SRC)) {
  const src = readFileSync(f, 'utf8')
  // Nur park-fähige Dateien (importieren Parkbar). Wächter selbst + Mechanik raus.
  if (!/from '[^']*\/park'/.test(src) && !/from '\.\/Parkbar'/.test(src)) continue
  if (f.includes('/components/park/')) continue
  const rel = f.replace(ROOT + '/', '')
  if (MECHANIK.includes(rel) || AUSSER_REICHWEITE(rel)) continue
  geprueft++
  const treffer = []
  for (const k of topLevelKoerper(src)) {
    // (A) nur in Körpern, die selbst eine <Parkbar> tragen (= Sicht, die parkt) —
    //     sonst ist es eine atomare Komponente, die der Aufrufer parkt.
    if (/<Parkbar\b/.test(k.body)) {
      treffer.push(...findeUnparkbareMarker(k.body, k.start, src, rel))
    }
    // (B) jeder render-Körper (Block) ohne jede Parkbar aber mit Anzeige.
    for (const rk of renderKoerper(k.body, k.start)) {
      if (istUnparkbarerBlock(rk.body)) {
        treffer.push({ datei: rel, zeile: zeileVon(src, rk.renderOffset), kind: 'render() ohne Parkbar', art: 'B' })
      }
    }
  }
  for (const t of treffer) {
    if (!ALLOWLIST.has(`${t.datei}:${t.kind}`)) verstoesse.push(t)
  }
}

if (verstoesse.length > 0) {
  console.error('\ncheck:parkbar-vollstaendig — un-parkbare Anzeige(n) in Park-Sichten:\n')
  for (const v of verstoesse.sort((a, b) => a.datei.localeCompare(b.datei) || a.zeile - b.zeile)) {
    const tag = v.art === 'A' ? `Anzeige \`${v.kind}\` außerhalb jeder <Parkbar>` : `Block-\`${v.kind}\` (ganzer Block un-parkbar)`
    console.error(`  ✗ ${v.datei}:${v.zeile} → ${tag}`)
  }
  console.error(
    '\nDoktrin: JEDE Anzeige in einer Park-Sicht ist einzeln parkbar (→ Block vollständig auflösbar).\n' +
    '  • Anzeige in eine <Parkbar id=… titel=…> hüllen (KpiStrip parkt Kacheln selbst via parkId).\n' +
    '  • Bewusste Ausnahme (echtes Layout) → scripts/parkbar-vollstaendig-allowlist.json ("datei:kind").\n',
  )
  process.exit(1)
}

console.log(`\ncheck:parkbar-vollstaendig — ${geprueft} Park-Sichten geprüft, keine un-parkbare Anzeige.`)
console.log('✅ Vollständigkeit: jede Anzeige parkbar → jeder Block vollständig auflösbar.')
