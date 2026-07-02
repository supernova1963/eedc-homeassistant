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

console.log(`check:v4links — ${treffer} v4-interne Hash-Links, alle /v4/-relativ (kein V3-Sprung).`)
console.log('✅ IA-V4: keine V4→V3-Hash-Links unter src/v4/.')
