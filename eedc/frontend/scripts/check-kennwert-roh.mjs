#!/usr/bin/env node
/**
 * check-kennwert-roh.mjs — die Client-Hälfte von ADR-002/P3-a (A26/N106).
 *
 * **Die Regel:** ANZEIGE und RECHNUNG lesen `leistung_kwp_effektiv`,
 * FORMULARE und WIZARDS die Rohspalte `leistung_kwp`.
 *
 * Warum es diese Trennung gibt — beide Richtungen sind schon schiefgegangen:
 *  - Läse die Anzeige die Rohspalte, fehlte die Nennleistung jedem Nutzer, der
 *    sie nur im `parameter`-JSON gepflegt hat (Import-/Altbestand, #229), und
 *    die kWp-Verteilung in `v4/komponentenAdapter.tsx` gäbe seinem Modul 0 und
 *    den übrigen zu viel.
 *  - Läse ein EINGABEFELD den abgeleiteten Wert, schriebe das nächste Speichern
 *    ihn in die Spalte — der Client machte aus einer Ableitung dauerhaft
 *    Stammdaten. Genau diese Falle hat backend-seitig den JSON-Export in die
 *    Allowlist gebracht (`P3A_BASELINE_AUSNAHMEN`, json_operations.py::inv).
 *
 * Der Backend-Wächter (`test_wurzelmuster_konformitaet.py::test_p3a_*`) sagt
 * über den Client **nichts** — das ist Grenze (c) der P3-a-Zeile in ADR-002.
 * Dieses Skript schließt sie.
 *
 * **Mechanik, bewusst dieselbe wie backend-seitig:** keine Typinferenz, sondern
 * Empfänger-Namensheuristik + `Datei::Empfänger`-Allowlist mit Klartext-
 * Begründung je Eintrag. Ein Empfänger, der `anlage` heißt, aber eine
 * Investition hält, ist falsch-negativ per Konstruktion — dieselbe bewusste
 * Grenze, die der Backend-Wächter zieht.
 *
 * **Grenzen (am Code gemessen, keine Fußnote):**
 *  (a) Nur die Attributform. `x['leistung_kwp']` wird nicht erfasst — heute
 *      existiert im Baum keine einzige (gemessen 2026-07-27).
 *  (b) Kommentare werden gestrippt, Strings nicht: ein `'leistung_kwp'` als
 *      Objekt-Schlüssel ohne Punkt davor matcht ohnehin nicht.
 *  (c) Nur `leistung_kwp`. `neigung_grad`/`ausrichtung` bewusst nicht — die
 *      SoT-Helper defaulten dort auf 35°/Süd und können „fehlt" nicht von
 *      „gepflegt" unterscheiden (ADR-002 §„Was noch nicht gewächtert ist").
 *
 * `--inventur` gibt den Ist-Bestand als Allowlist-Zeilen aus.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')

/** Empfänger, die baumweit KEINE Investition sind — dieselbe Konstruktion wie
 *  `P3A_ERLAUBTE_EMPFAENGER` im Backend-Wächter.
 *
 *  `anlage` ist ein eigenes Modell mit eigener Spalte `Anlage.leistung_kwp`
 *  (Anlagen-Gesamtleistung); es hat kein `parameter`-JSON mit einer zweiten
 *  kWp-Quelle, es gibt dort also gar keinen abweichenden effektiven Wert.
 *  `formData` ist Formular-State (die Eingabe selbst), nie eine API-Antwort. */
const ERLAUBTE_EMPFAENGER = new Set(['anlage', 'formData', 'Investition'])

/** `Datei::Empfänger` → Begründung. Baseline: 0 unklassifizierte Treffer.
 *
 *  Zwei Gattungen, und nur zwei:
 *   (E) EINGABE — schreibt die Spalte und MUSS sie roh lesen.
 *   (F) FREMDES OBJEKT — heißt nur genauso, ist aber keine Investition aus der
 *       Investitionen-API (eigene Response mit eigener Provenance). */
const ALLOWLIST = new Map([
  // ── (E) Eingabe: Formulare und Wizards, die die Spalte schreiben ──────────
  ['src/components/forms/InvestitionForm.tsx::investition',
    '(E) Vorbelegung des Eingabefeldes aus der zu bearbeitenden Investition — der abgeleitete Wert würde beim Speichern in die Spalte wandern.'],
  ['src/components/setup-wizard/sections/SetupInvestitionForm.tsx::investition',
    '(E) Eingabefeld „Leistung (kWp)" im Setup-Wizard (value + onChange auf derselben Spalte).'],
  ['src/components/forms/AnlageForm.tsx::current',
    '(E) `feldRefs.current.leistung_kwp` — Ref-Schlüssel für den Fehler-Fokus, gar keine Wertlesung (und die Anlage, nicht die Investition).'],

  // ── (F) Gleichnamiges Feld auf einer ANDEREN Response ─────────────────────
  ['src/components/live/EnergieFluss.tsx::k',
    '(F) Live-Komponenten-Response. Liefert seit A24-2 (live_komponenten_builder.py) bereits den EFFEKTIVEN Wert über `get_erzeuger_kwp` — hier ist nichts mehr zu heilen.'],
  ['src/components/prognose/PvStringsTeile.tsx::s',
    '(F) `/cockpit/pv-strings-gesamtlaufzeit`-Response (PV-String), eigene Provenance seit A4 — keine Investition.'],
  ['src/components/pv/PVStringVergleich.tsx::s',
    '(F) dieselbe PV-Strings-Response wie PvStringsTeile.'],
  ['src/pages/PVGISSettingsTeile.tsx::m',
    '(F) `PVModulPrognose` aus einer gespeicherten PVGIS-Prognose (Vorschau) — Prognose-Objekt, keine Investition.'],
  ['src/pages/PVGISSettingsTeile.tsx::mod',
    '(F) dieselbe PVGIS-Prognose, zweite Ansicht (gespeicherte Prognose).'],
  ['src/pages/CloudImportWizard.tsx::a',
    '(F) Anlagen-Auswahlliste des Cloud-Imports (`anlagen.map(a => …)`) — Anlagen-Gesamtleistung im Label.'],
  ['src/pages/CustomImportWizard.tsx::a',
    '(F) dieselbe Anlagen-Auswahlliste im Custom-Import.'],
  ['src/pages/DataImportWizard.tsx::a',
    '(F) dieselbe Anlagen-Auswahlliste im Daten-Import.'],
])

// ---------------------------------------------------------------------------

function quellDateien(dir) {
  const out = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) out.push(...quellDateien(p))
    else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name)) out.push(p)
  }
  return out
}

const rel = (f) => relative(ROOT, f).replaceAll('\\', '/')
/** Block- und Ganz-Zeilen-Kommentare strippen (Doku nennt die Rohspalte oft beim Namen). */
const stripComments = (src) => src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')

/** `.leistung_kwp` / `?.leistung_kwp` — `leistung_kwp_effektiv` fällt durch die Lookahead. */
const ZUGRIFF = /\??\.\s*leistung_kwp(?![\w$])/g

const treffer = []  // { datei, zeile, empfaenger }
for (const f of quellDateien(join(ROOT, 'src'))) {
  const src = stripComments(readFileSync(f, 'utf8'))
  let m
  while ((m = ZUGRIFF.exec(src)) !== null) {
    const davor = src.slice(0, m.index).replace(/\s+$/, '')
    // Empfänger-Name — oder eine Marke, wenn es keiner ist (`invs[0].leistung_kwp`,
    // `ladeInv().leistung_kwp`). Marken matchen keinen Allowlist-Schlüssel und
    // gelten damit als Verstoß: fail-loud statt stillschweigend durchlassen,
    // genau wie `_p3a_empfaengername` im Backend-Wächter.
    const name = /([\w$]+)$/.exec(davor)
    treffer.push({
      datei: rel(f),
      zeile: src.slice(0, m.index).split('\n').length,
      empfaenger: name ? name[1] : '<komplex>',
    })
  }
}

if (process.argv.includes('--inventur')) {
  const gesehen = new Map()
  for (const t of treffer) {
    const k = `${t.datei}::${t.empfaenger}`
    gesehen.set(k, (gesehen.get(k) ?? 0) + 1)
  }
  for (const [k, n] of [...gesehen].sort()) console.log(`  ['${k}', ''],  // ${n}×`)
  process.exit(0)
}

let fehler = 0
const meld = (msg) => { fehler++; console.error('✗ ' + msg) }

const HINWEIS = (
  '\nAnzeige/Rechnung lesen `leistung_kwp_effektiv` (vom Server berechnet, ' +
  'inkl. `parameter`-JSON-Fallback bei Erzeugern — #229). Die Rohspalte ' +
  '`leistung_kwp` ist NUR für Eingabefelder da, die sie auch schreiben.\n' +
  'Wer bewusst die Rohspalte liest (Eingabe) oder gar keine Investition liest ' +
  '(Anlage, PV-String, PVGIS-Prognose, Live-Komponente), trägt sich mit ' +
  'Klartext-Begründung in ALLOWLIST ein — Form `datei.tsx::empfaenger`.'
)

const benutzt = new Set()
for (const t of treffer) {
  if (ERLAUBTE_EMPFAENGER.has(t.empfaenger)) continue
  const key = `${t.datei}::${t.empfaenger}`
  if (ALLOWLIST.has(key)) { benutzt.add(key); continue }
  meld(`Rohe Investitions-kWp: ${t.datei}:${t.zeile} — Zugriff auf '${t.empfaenger}.leistung_kwp'  (Allowlist-Schlüssel: ${key})`)
}
for (const [key, grund] of ALLOWLIST) {
  if (!benutzt.has(key)) meld(`Allowlist-Eintrag ohne Treffer: ${key} — Eintrag entfernen (verwaiste Ausnahme deckt sonst später einen echten Treffer). Begründung war: ${grund}`)
}

if (fehler) {
  console.error(`\ncheck:kennwert-roh — ${fehler} Abweichung(en).${HINWEIS}`)
  process.exit(1)
}
console.log(
  `✓ check:kennwert-roh — 0 rohe Kennwert-Zugriffe außerhalb der Eingabe ` +
  `(${treffer.length} Zugriffe geprüft, ${ALLOWLIST.size} klassifiziert, ` +
  `${ERLAUBTE_EMPFAENGER.size} baumweit erlaubte Empfänger).`,
)
