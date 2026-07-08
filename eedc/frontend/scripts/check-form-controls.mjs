#!/usr/bin/env node
/**
 * check-form-controls.mjs — SoT-Garantie für Formular-Controls (Style-Guide
 * Teil D, M1 / D6; Fundament „Formulare V4").
 *
 * Regel (M1): In den dedizierten Formular-Komponenten (`src/components/forms/**`,
 * **rekursiv** inkl. `sections/**`) KEINE rohen `<select>` / `<textarea>` /
 * `<input>` / `<label>` — dort sind die SoT-Controls Pflicht: `Input` · `Select` ·
 * `Switch` · `Textarea` · `DatumFeld` · `RadioGroup` (mit interner Feld-Anatomie
 * inkl. Label). So kann der Drift, den R17 einsammelte (D17-7/-8/-10, uneinheitliche
 * Pflicht-Marker), nicht zurück.
 *
 * Rekursions-Fund (Slice 5): der Scan lief zuvor NICHT rekursiv → ausgelagerte
 * Sektionen (`sections/SonstigePositionenFields`) schmuggelten rohe Primitive am
 * Wächter vorbei. Beim Split von InvestitionForm in `sections/**` muss der Guard
 * rekursiv sein, sonst wären die ausgelagerten Dateien ungegatet
 * ([[feedback_verifiziert_nur_was_check_abdeckt]]).
 *
 * Scope-Grenze (bewusst): nur `src/components/forms/**`. Formulare, die noch inline
 * in Seiten leben (z. B. StrompreisForm in `pages/StrompreiseTeile.tsx`), sind hier
 * NICHT erfasst — die Seiten enthalten legitime Nicht-Formular-Primitive, eine
 * datei-weite Grep-Regel würde dort false-positiven. Wandern solche Formulare in
 * `components/forms/`, greift der Wächter automatisch.
 *
 * Allowlist: Formulare, die noch nicht auf V4-SoT gehoben sind (kommen slice-weise).
 * Ein migriertes Formular wird HIER entfernt → ab dann bewacht. Ziel: leere Liste
 * — mit Slice 5 (InvestitionForm-Split + SonstigePositionenFields) **erreicht**.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
// Bewachte Formular-Pfade (rekursiv): dedizierte Formulare + Setup-Wizard-Steps
// (Slice 6 auf V4-SoT gehoben → hier mit aufgenommen, damit der Drift nicht zurück).
const FORM_ROOTS = [
  join(ROOT, 'src', 'components', 'forms'),
  join(ROOT, 'src', 'components', 'setup-wizard'),
]

// Dauer-Ausnahme (kein pending-Migration): `WelcomeStep` nutzt einen versteckten
// `<input type="file">` für den JSON-Restore — dafür gibt es kein SoT-Äquivalent
// (BildUpload ist bildspezifisch). Sonst leer: alle Formulare SoT-rein.
const ALLOWLIST = new Set(['WelcomeStep.tsx'])

const ROH = /<(select|textarea|input|label)\b/g

const lineOf = (src, index) => src.slice(0, index).split('\n').length

/** Rekursiv alle .tsx (ohne Tests) unter `dir` einsammeln. */
function tsxFiles(dir) {
  const out = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) out.push(...tsxFiles(p))
    else if (name.endsWith('.tsx') && !name.endsWith('.test.tsx')) out.push(p)
  }
  return out
}

const formFiles = FORM_ROOTS.flatMap(tsxFiles)

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
