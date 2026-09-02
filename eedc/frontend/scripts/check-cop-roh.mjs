#!/usr/bin/env node
/**
 * check-cop-roh.mjs — die Client-Hälfte von ADR-002/**P12** (02.09.2026).
 *
 * **Die Regel:** Der Client bildet **keine Arbeitszahl**. Ein Quotient aus einer
 * Wärme- und einer Stromgröße entsteht ausschließlich in
 * `core/berechnungen/waermepumpe_kennzahl.py::arbeitszahl`; der Client *liest*
 * das Ergebnis samt Grund aus der Antwort.
 *
 * **Warum es diesen Wächter gibt.** Die Arbeitszahl ist die einzige Kennzahl in
 * eedc, die **nicht erscheinen darf**, wenn Zähler und Nenner verschieden
 * abgegrenzt sind (SOLL §1, §4.2, §5 — Bauartmischung · Geräte ohne
 * Wärmemeldung · Heizstab am Zähler · gerechnete statt gemessener Wärme ·
 * funktionsfremder Strom im Nenner). Eine rohe Division kann von alldem nichts
 * wissen. Genau daran ist die Fläche dreimal gescheitert:
 *
 *   • **W-3**  — dieselbe Frage an drei Stellen, eine davon im Client
 *   • **W-15** — der Hub sagte 2,31, das Cockpit 3,00 für denselben Monat
 *   • **P12**  — Werte-Tabelle, HA-Sensor, Jahresbericht-PDF und der
 *                Community-Payload rechneten am 02.09.2026 noch selbst
 *
 * Der Melder-Fall dazu: eine Anlage mit Wärmepumpe **und** Split-Klimaanlage.
 * Beide Ströme im Nenner, nur eine Wärme im Zähler ⇒ angezeigt **0,7**, während
 * die Wärmepumpe selbst bei **2,2** liegt. Die Zahl beschreibt kein Gerät der
 * Anlage — sie bewegt sich mit dem Betrieb des ungezählten Geräts.
 *
 * **Was der Wächter sucht:** eine Division, deren Zähler eine *Wärme*- und
 * deren Nenner eine *Strom*-Größe benennt — in beiden Schreibweisen (`waerme`
 * und `heiz*`), ohne Rücksicht auf Präfixe (`wp_waerme`, `gesamtWaerme`).
 *
 * **Grenzen — am Code gemessen, keine Fußnote:**
 *  (a) **Namensbasiert.** Wer die Größen erst in neutral benannte Variablen legt
 *      (`const a = ...; const b = ...; a / b`), läuft vorbei. Dieselbe Grenze
 *      wie bei `check:co2-roh` (d) und beim Dienstlast-Wächter in ADR-001.
 *  (b) **Nur der Client.** Die Backend-Hälfte hält
 *      `test_wurzelmuster_konformitaet.py::test_p11_*` baumweit.
 *  (c) **Kommentare UND String-Literale** werden neutralisiert, beide
 *      zeilentreu. Ein Quotient in einem String ist keine Rechnung, sondern ein
 *      Anzeigetext — und davon gibt es drei im Baum, die alle richtig sind
 *      (`fieldDefinitions.ts` „COP = Heizwärme / Strom",
 *      `CommunityKomponentenTeile.tsx` „Wärmeenergie / Stromverbrauch" 2×).
 *      Die erste Fassung fing sie und hätte den Wächter unbrauchbar gemacht:
 *      Wer drei richtige Treffer wegdrücken muss, drückt beim vierten auch den
 *      falschen weg.
 *
 * **Beidseitig gesprengt (02.09.2026):** `wp_waerme / wp_strom` und
 * `gesamtWaerme/gesamtStrom` werden gefangen; `wp_waerme + wp_strom`,
 * `pv_kwh / strom_kwh` und `wp_waerme / flaeche` laufen durch. Ein Prüfer ist
 * erst nach seinem Sprengsatz ein Prüfer.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')

/**
 * Zähler = Wärmegröße, Nenner = Stromgröße. `[\w.]*` deckt Präfixe und
 * Objektzugriffe (`md.wp_waerme_kwh`), `[_a-zA-Z]*` die Suffixe (`_kwh`).
 * Die Wärme-Seite kennt beide Schreibweisen der Fläche: `waerme` und `heiz`.
 */
const WAERME = String.raw`[\w.]*(?:[wW]aerme|[wW]ärme|[hH]eiz)[\w.]*`
const STROM = String.raw`[\w.]*[sS]trom[\w.]*`
const ROHE_DIVISION = new RegExp(String.raw`\b${WAERME}\s*/\s*${STROM}\b`, 'g')

const stripComments = (src) =>
  src
    .replace(/\/\*[\s\S]*?\*\//g, (t) => t.replace(/[^\n]/g, ' '))
    .replace(/^[ \t]*\/\/.*$/gm, '')

/**
 * String-Literale neutralisieren — zeilentreu, damit die Fundmeldung weiter auf
 * die richtige Zeile zeigt (dieselbe Falle wie bei den Block-Kommentaren, N-165).
 * Template-Literale bleiben absichtlich stehen: `${a / b}` IST eine Rechnung.
 */
const stripStrings = (src) =>
  src.replace(/'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"/g,
    (t) => t.replace(/[^\n]/g, ' '))

function quellDateien(dir) {
  const out = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) out.push(...quellDateien(p))
    else if (/\.tsx?$/.test(name)) out.push(p)
  }
  return out
}

const rel = (f) => relative(ROOT, f).replaceAll('\\', '/')

let geprueft = 0
const verstoesse = []

for (const f of quellDateien(join(ROOT, 'src'))) {
  const src = stripStrings(stripComments(readFileSync(f, 'utf8')))
  let m
  ROHE_DIVISION.lastIndex = 0
  while ((m = ROHE_DIVISION.exec(src)) !== null) {
    geprueft++
    const zeile = src.slice(0, m.index).split('\n').length
    verstoesse.push({ datei: rel(f), zeile, text: m[0].trim() })
  }
}

if (verstoesse.length > 0) {
  console.error(`\n✗ check:cop-roh — ${verstoesse.length} rohe Arbeitszahl-Division(en):\n`)
  for (const v of verstoesse) console.error(`  ${v.datei}:${v.zeile}  ${v.text}`)
  console.error(`
  Die Arbeitszahl entsteht im Layer (ADR-002/P12), nicht im Client.
  Sie darf NICHT erscheinen, wenn Zaehler und Nenner verschieden abgegrenzt
  sind — das weiss nur 'core/berechnungen/waermepumpe_kennzahl.py::arbeitszahl'.
  Lies den Wert samt '..._grund' aus der Antwort.\n`)
  process.exit(1)
}

console.log(`✓ check:cop-roh — 0 rohe Arbeitszahl-Divisionen (${geprueft} Treffer geprueft)`)
