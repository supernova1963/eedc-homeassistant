#!/usr/bin/env node
/**
 * check-v4links.mjs — „V4 verlinkt V3 NIE"-Garantie für die IA-V4-Sichten.
 *
 * Hintergrund (Gernot-Fund 2026-07-02): der Komponenten-Hub verlinkte pro Komponente
 * noch nach V3 (`const EDIT_INFOTHEK = '#/einstellungen/infothek'` → `href={EDIT_INFOTHEK}`)
 * → Sprung aus der V4-Oberfläche in eine V3-Seite (Sackgasse ohne Rückweg unterm Flag).
 * Die manuelle navigate-Inventur hatte das übersehen, weil der Link über eine KONSTANTE
 * lief, nicht über ein `href="#/…"`-Literal. Dieser Check gießt die Regel in ein Gate,
 * unabhängig davon, ob der Link Attribut, Konstante oder crossLink ist.
 *
 * Regel: KEIN Hash-Link-Literal `'#/…'` / `"#/…"` unter `src/v4/**`, das nicht mit
 * `#/v4/` beginnt. Innerhalb von `/v4` muss jeder App-interne Hash-Link auf eine
 * `/v4/*`-Route zeigen. Re-kategorisierte Einstellungs-Ziele → `config/v3ZuV4Route`.
 *
 * Bewusst NICHT im Scope: `src/pages/**` (geteilte `*Teile.tsx` rendern in BEIDEN
 * Welten → route-basierter Präfix via `useV4Basis`, dort ist `#/einstellungen/…`
 * legitim) sowie `navigate('/…')`-Aufrufe auf Donor-Ziele ohne V4-Heimat
 * (Monatsabschluss/CSV-Import → R6). Dieser Guard deckt die Hash-Link-Literale ab,
 * die den 2026-07-02-Blind-Spot ausmachten.
 *
 * Ausgabe: "check:v4links — N v4-interne Hash-Links, alle /v4/-relativ".
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const V4 = join(ROOT, 'src', 'v4')

/** Rekursiv alle .tsx (ohne Tests) unter `dir` einsammeln. */
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

function lineOf(src, index) {
  return src.slice(0, index).split('\n').length
}

// App-interner Hash-Link-Literal: Quote, `#/`, Pfad bis Quote. Reine Anker (`#top`,
// kein Slash) matchen nicht. Verstoß = jeder, der NICHT mit `#/v4/` weitergeht.
const HASHLINK = /['"]#\/[a-z][^'"]*['"]/g

const violations = []
let treffer = 0

for (const file of tsxFiles(V4)) {
  const src = readFileSync(file, 'utf8')
  let m
  while ((m = HASHLINK.exec(src)) !== null) {
    treffer++
    if (!m[0].startsWith("'#/v4/") && !m[0].startsWith('"#/v4/')) {
      violations.push(`${relative(ROOT, file)}:${lineOf(src, m.index)}  ${m[0]} → auf eine #/v4/…-Route umbiegen`)
    }
  }
}

if (violations.length > 0) {
  console.log(`check:v4links — ${violations.length} V3-Hash-Link(s) unter src/v4/`)
  console.error(`\n❌ ${violations.length} Hash-Link(s) aus der IA-V4 in eine V3-Seite (Sackgasse):`)
  for (const v of violations) console.error('  · ' + v)
  console.error(
    '\nFix: den Link auf die V4-Route umbiegen (`#/v4/einstellungen/<kategorie>` …). ' +
      'Einstellungs-Ziele re-kategorisiert → `config/v3ZuV4Route`. In geteilten ' +
      '`pages/*Teile.tsx` (V3+V4) stattdessen `useV4Basis()` nutzen.',
  )
  process.exit(1)
}

// ── Regel 2: V3→V4-Totlinks (Fund 2026-07-18, HAExportSettingsTeile:542) ──
// AUSSERHALB src/v4 ist ein hartes '#/v4/…'-Literal im flag-off-Release-Build
// eine TOTE Route (kein Catch-all → leere Seite). Erlaubt nur mit Flag-/
// Kontext-Gate in unmittelbarer Nähe (IA_V4 / v4Basis / imOverlay) oder per
// Allowlist für Dateien, die ausschließlich von src/v4 importiert werden
// (flag-off tree-geshaked — Eintrag = belegte Import-Kette, nicht Bequemlichkeit).

const V4LINK_ALLOWLIST = new Set([
  // Nur von v4/cockpit/CockpitAussichtV4 importiert; im V3-Build nicht im Bundle.
  'src/components/aussicht/AussichtTeile.tsx',
])
const GATE = /IA_V4|v4Basis|imOverlay/
const V4HASH = /['"]#\/v4\/[^'"]*['"]/g
const SRC = join(ROOT, 'src')

const totlinks = []
for (const file of tsxFiles(SRC)) {
  const rel = relative(ROOT, file).split('\\').join('/')
  if (rel.startsWith('src/v4/') || rel.startsWith('src/test/')) continue
  if (V4LINK_ALLOWLIST.has(rel)) continue
  const src = readFileSync(file, 'utf8')
  const lines = src.split('\n')
  let m
  while ((m = V4HASH.exec(src)) !== null) {
    const ln = lineOf(src, m.index)
    const zeile = (lines[ln - 1] || '').trim()
    if (zeile.startsWith('*') || zeile.startsWith('//')) continue
    const kontext = lines.slice(Math.max(0, ln - 6), ln + 5).join('\n')
    if (!GATE.test(kontext)) {
      totlinks.push(`${rel}:${ln}  ${m[0]} → ohne IA_V4-/v4Basis-/imOverlay-Gate = tote Route im V3-Build`)
    }
  }
}

if (totlinks.length > 0) {
  console.log(`check:v4links — ${totlinks.length} ungegatete(r) #/v4-Link(s) außerhalb src/v4/`)
  console.error(`\n❌ ${totlinks.length} harte(r) #/v4-Link(s) in V3-erreichbarem Code (flag-off = leere Seite):`)
  for (const v of totlinks) console.error('  · ' + v)
  console.error(
    '\nFix: Link per `IA_V4 ? \'#/v4/…\' : \'#/<v3-route>\'` (bzw. useV4Basis in geteilten ' +
      'Teile-Dateien) gaten. Datei nachweislich v4-only importiert → V4LINK_ALLOWLIST ' +
      'mit Import-Kette im Kommentar.',
  )
  process.exit(1)
}

console.log(`check:v4links — ${treffer} v4-interne Hash-Links, alle /v4/-relativ (kein V3-Sprung).`)
console.log('✅ IA-V4: keine V4→V3-Hash-Links unter src/v4/ und keine ungegateten V3→V4-Totlinks.')
