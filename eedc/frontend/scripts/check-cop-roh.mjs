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
 *  (b) **Nur der Client** — und sie ist die **schwächere** der beiden Hälften.
 *      Die Backend-Hälfte hält `test_wurzelmuster_konformitaet.py::
 *      test_p12_arbeitszahl_nur_im_layer` baumweit, und zwar über den **AST**:
 *      sie sammelt die Namen unterhalb von Zähler und Nenner rekursiv und ist
 *      damit gegen Schreibweisen strukturell immun. Gemessen am 02.09.2026:
 *      derselbe Sprengsatz `(heiz_kwh + ww_kwh) / wp_strom_kwh`, an dem dieser
 *      Wächter bis N-369 vorbeilief, wird dort ohne Zutun gefangen
 *      (`'heiz_kwh ww_kwh' / 'wp_strom_kwh'`).
 *      ⚠ **Wer hier eine neue Schreibweise ergänzt, ergänzt sie nur hier** —
 *      im Backend gibt es nichts nachzuziehen. Und umgekehrt: eine Form, die
 *      der Backend-Wächter meldet, kann dieser hier trotzdem übersehen.
 *      ⛔ **Hier stand bis 02.09. `test_p11_*`** — das ist ein **anderer,
 *      existierender** Wächter (PV-Erzeuger-Selektor, N-266). Der Verweis zeigte
 *      also nicht ins Leere, sondern auf die **falsche Invariante**; ein
 *      Grep-Sweep beim Umbenennen P11 → P12 hat ihn übersehen, weil er auf
 *      `ADR-002/P11` suchte und hier nur `test_p11_*` steht.
 *  (c) **Kommentare UND String-Literale** werden neutralisiert, beide
 *      zeilentreu. Ein Quotient in einem String ist keine Rechnung, sondern ein
 *      Anzeigetext — und davon gibt es drei im Baum, die alle richtig sind
 *      (`fieldDefinitions.ts` „COP = Heizwärme / Strom",
 *      `CommunityKomponentenTeile.tsx` „Wärmeenergie / Stromverbrauch" 2×).
 *      Die erste Fassung fing sie und hätte den Wächter unbrauchbar gemacht:
 *      Wer drei richtige Treffer wegdrücken muss, drückt beim vierten auch den
 *      falschen weg.
 *
 * **Beidseitig gesprengt — zehn Fälle, fünf je Seite (02.09.2026, erweitert mit N-369):**
 *
 *   GEFANGEN                                                       DURCH
 *   `wp_waerme / wp_strom`                                         `wp_waerme + wp_strom`
 *   `gesamtWaerme/gesamtStrom`                                     `pv_kwh / strom_kwh`
 *   `(heiz + ww) / strom`                          ← N-369         `wp_waerme / flaeche`
 *   `(md.heizenergie_kwh + md.warmwasser_kwh) / md.stromverbrauch_kwh`  `(a + b) / strom`  ← Grenze (a)
 *   `(ww + heiz) / strom`  (Summanden vertauscht)                  `(ladung + entladung) / kapazitaet`
 *
 * Ein Prüfer ist erst nach seinem Sprengsatz ein Prüfer — und die rechte Spalte
 * gehört genauso dazu: `(a + b) / strom` MUSS durchlaufen, sonst wäre Grenze (a)
 * stillschweigend verschoben statt entschieden.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')

/**
 * Zähler = Wärmegröße, Nenner = Stromgröße. `[\w.]*` deckt Präfixe und
 * Objektzugriffe (`md.wp_waerme_kwh`), `[_a-zA-Z]*` die Suffixe (`_kwh`).
 * Die Wärme-Seite kennt beide Schreibweisen der Fläche: `waerme` und `heiz`.
 *
 * ⭐ **Seit N-369 (02.09.2026) auch die KLAMMER-SUMME im Zähler.** Der Wächter
 * fing `wp_waerme / wp_strom`, aber nicht `(heiz + ww) / strom` — und genau so
 * stand es in `WaermepumpeCharts.tsx:123`, der JAZ-Spalte des Wärmepumpen-Hubs.
 * ⛔ **Das war NICHT die dokumentierte Grenze (a) unten:** Die Namen sind
 * sprechend (`heiz`, `strom`), nur die Klammer brach das Muster. Und *Heizung +
 * Warmwasser* ist auf dieser Fläche die Standard-Schreibweise für „Wärme" — der
 * Wächter war damit ausgerechnet für die wahrscheinlichste Bauform blind.
 * Er verlangt weiterhin, dass **ein** Summand eine Wärmegröße benennt; eine
 * Klammer aus lauter neutralen Namen bleibt Grenze (a).
 */
const WAERME = String.raw`[\w.]*(?:[wW]aerme|[wW]ärme|[hH]eiz)[\w.]*`
const STROM = String.raw`[\w.]*[sS]trom[\w.]*`
//: Eine Klammer-Summe, in der MINDESTENS ein Summand eine Wärmegröße benennt.
//: `[^()]*` hält sie flach — verschachtelte Klammern fängt der Wächter bewusst
//: nicht, sie wären ohne Parser nicht sicher abzugrenzen.
const WAERME_SUMME = String.raw`\((?:[^()]*\b${WAERME}\b[^()]*)\)`
const ROHE_DIVISION = new RegExp(String.raw`(?:${WAERME_SUMME}|\b${WAERME})\s*/\s*${STROM}\b`, 'g')

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
