#!/usr/bin/env node
/**
 * check-form-controls.mjs — SoT-Garantie für Formular-Controls (Style-Guide
 * Teil D, M1 / D6; Fundament „Formulare V4").
 *
 * Regel (M1): In den dedizierten Formular-Komponenten (`src/components/forms/**`)
 * KEINE rohen `<select>` / `<textarea>` / `<input>` / `<label>` — dort sind die
 * SoT-Controls Pflicht: `Input` · `Select` · `Switch` · `Textarea` · `DatumFeld`
 * · `RadioGroup` (mit interner Feld-Anatomie inkl. Label). So kann der Drift, den
 * R17 einsammelte (D17-7/-8/-10, uneinheitliche Pflicht-Marker), nicht zurück.
 *
 * Scope-Grenze (bewusst): nur `src/components/forms/**`. Formulare, die noch inline
 * in Seiten leben (z. B. StrompreisForm in `pages/StrompreiseTeile.tsx`), sind hier
 * NICHT erfasst — die Seiten enthalten legitime Nicht-Formular-Primitive, eine
 * datei-weite Grep-Regel würde dort false-positiven. Wandern solche Formulare in
 * `components/forms/`, greift der Wächter automatisch.
 *
 * Allowlist: Formulare, die noch nicht auf V4-SoT gehoben sind (kommen slice-weise).
 * Ein migriertes Formular wird HIER entfernt → ab dann bewacht. Ziel: leere Liste.
 */
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const FORMS = join(ROOT, 'src', 'components', 'forms')

// Noch nicht auf V4-SoT gehoben (Umbau-Reihenfolge KONZEPT-FORMULARE-V4 §3):
//   InvestitionForm (+ SonstigePositionenFields) = Slice 5.
// Beim Migrieren des jeweiligen Formulars den Eintrag entfernen (MonatsdatenForm
// = Slice 3, InfothekForm = Slice 4 — migriert → entfernt).
const ALLOWLIST = new Set([
  'InvestitionForm.tsx',
  'SonstigePositionenFields.tsx',
])

const ROH = /<(select|textarea|input|label)\b/g

const lineOf = (src, index) => src.slice(0, index).split('\n').length

const formFiles = readdirSync(FORMS)
  .filter((n) => n.endsWith('.tsx') && !n.endsWith('.test.tsx'))
  .map((n) => join(FORMS, n))

let bewacht = 0
const violations = []

for (const file of formFiles) {
  const base = file.split('/').pop()
  if (ALLOWLIST.has(base)) continue
  bewacht++
  const src = readFileSync(file, 'utf8')
  let m
  while ((m = ROH.exec(src)) !== null) {
    violations.push(`${relative(ROOT, file)}:${lineOf(src, m.index)} rohes <${m[1]}> — SoT-Control nutzen (Input/Select/Switch/Textarea/DatumFeld/RadioGroup)`)
  }
}

if (violations.length > 0) {
  console.log(`check:form-controls — ${violations.length} rohe(s) Formular-Primitiv(e) in migrierten forms/`)
  console.error(`\n❌ ${violations.length} rohe(s) Control(s) statt SoT (Style-Guide Teil D, M1):`)
  for (const v of violations) console.error('  · ' + v)
  console.error(
    '\nFix: `Input`/`Select`/`Switch`/`Textarea`/`DatumFeld`/`RadioGroup` aus components/ui ' +
      'statt roher <select>/<textarea>/<input>/<label>. Label + Pflicht-Marker + Hint/Fehler ' +
      'liefert der Control (Feld-Anatomie D1). Sonderfall → in die Allowlist im Check aufnehmen.',
  )
  process.exit(1)
}

const pending = [...ALLOWLIST].sort().join(', ')
console.log(`check:form-controls — ${bewacht} migrierte Formular-Datei(en) SoT-rein · ${ALLOWLIST.size} noch offen (${pending}).`)
console.log('✅ Formular-Controls: keine rohen Primitive in den migrierten forms/ (M1).')
