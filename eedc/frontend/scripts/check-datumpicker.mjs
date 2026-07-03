#!/usr/bin/env node
/**
 * check-datumpicker.mjs — SoT-Garantie für Datums-/Monatsfelder in der IA-V4
 * (Slice A, D13-4/9/11/12, detLAN #105/#106/#107).
 *
 * Hintergrund: detLAN sah zwei Picker-Welten nebeneinander — ein helles Custom-
 * Monatsraster UND native `<input type=date/month>` (dunkler OS-Kalender, anderes
 * Icon, mobil zu groß, im Leer-Zustand geclippt). Vereinheitlicht auf EINE SoT
 * `components/ui/DatumPicker.tsx` (`<DatumPicker modus="monat|tag">`). Damit der
 * Drift nicht zurückkehrt, blockt dieser Check jedes native Datums-/Monatsfeld
 * unter `src/v4/`.
 *
 * Regel: KEIN `<input type="date">` / `<input type="month">` im Scope —
 * dort ist der `DatumPicker` (bzw. die Formular-Hülle `DatumFeld`) Pflicht.
 * Scope (D14-13, Entscheid Gernot 2026-07-03 — Slice-A-Ausnahme für die
 * Einstellungen aufgehoben): `src/v4/**` + die Einstellungen-Formulare
 * (`src/components/forms/**`, `src/pages/*Teile.tsx`). Setup-Wizard und
 * Repair-Werkbank bleiben bewusst nativ (der Dark-Icon-Fix in `index.css`
 * deckt sie ab); übrige Legacy-Seiten (`src/pages/**`) sind V3-only und
 * fallen mit dem Flip weg.
 *
 * Ausgabe: "check:datumpicker — N v4-Datumsfelder, alle über DatumPicker-SoT".
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const V4 = join(ROOT, 'src', 'v4')
const FORMS = join(ROOT, 'src', 'components', 'forms')
const PAGES = join(ROOT, 'src', 'pages')

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

// Natives Datums-/Monatsfeld: <input … type="date"|"month" …>. Der SoT-Picker
// nutzt intern KEIN natives date/month-Input mehr → jeder Treffer unter v4/ ist
// ein Verstoß.
const NATIVE = /type=["'](date|month)["']/g

// D14-13: Einstellungen-Formulare mit im Scope — src/components/forms/** komplett
// + die geteilten Einstellungen-Teile (pages/*Teile.tsx, nicht rekursiv).
const scopeFiles = [
  ...tsxFiles(V4),
  ...tsxFiles(FORMS),
  ...readdirSync(PAGES)
    .filter((n) => n.endsWith('Teile.tsx') && !n.endsWith('.test.tsx'))
    .map((n) => join(PAGES, n)),
]

let felder = 0
const violations = []

for (const file of scopeFiles) {
  const src = readFileSync(file, 'utf8')
  let m
  while ((m = NATIVE.exec(src)) !== null) {
    felder++
    violations.push(`${relative(ROOT, file)}:${lineOf(src, m.index)} natives <input type="${m[1]}"> — DatumPicker-/DatumFeld-SoT nutzen`)
  }
  // Zählung der SoT-Nutzungen für die Erfolgsmeldung (rein informativ).
  const sot = (src.match(/<(DatumPicker|DatumFeld)\b/g) || []).length
  felder += sot
}

if (violations.length > 0) {
  console.log(`check:datumpicker — ${violations.length} native(s) Datums-/Monatsfeld(er) im Scope (v4 + Einstellungen-Formulare)`)
  console.error(`\n❌ ${violations.length} native(s) Datums-/Monatsfeld(er) (statt DatumPicker-/DatumFeld-SoT):`)
  for (const v of violations) console.error('  · ' + v)
  console.error(
    '\nFix: `<DatumPicker modus="monat|tag" value=… onChange=… min=… max=… />` ' +
      '(aus components/ui/DatumPicker) statt `<input type="date|month">`. ' +
      'EIN Icon/Stil app-weit, Portal-Popover (nie geclippt), mobil-tauglich.',
  )
  process.exit(1)
}

console.log(`check:datumpicker — ${felder} Datumsfelder im Scope (v4 + Einstellungen-Formulare), alle über DatumPicker-SoT.`)
console.log('✅ Datums-/Monatsfelder: einheitlicher DatumPicker (D13-4/9/11/12 · D14-13).')
