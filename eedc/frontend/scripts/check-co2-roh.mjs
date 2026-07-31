#!/usr/bin/env node
/**
 * check-co2-roh.mjs — die Client-Hälfte der CO₂-Definition (ADR-001/DI-2, N-21).
 *
 * **Die Regel:** Der Client konstruiert **keine** CO₂-Menge. `CO2_FAKTOR_KG_KWH`
 * darf ausschließlich als *angezeigte Zahl* vorkommen — inklusive der einen
 * Einheiten-Umrechnung `× 1000` (kg/kWh → g/kWh in Methodik-Texten). Jede
 * andere Rechnung mit dem Faktor ist ein Verstoß.
 *
 * Warum es diesen Wächter gibt, und warum erst jetzt: `berechne_co2_bilanz` ist
 * seit DI-2 die einzige erlaubte Konstruktions-Stelle der CO₂-Kennzahl
 * (Eigenverbrauch × Strommix **plus** Wärmepumpe **plus** E-Mobilität). Die
 * Ablösung hat 2026 im Backend stattgefunden — im Client blieben **zwei
 * Überlebende** stehen, gemessen am 2026-07-31:
 *
 *   • `pages/auswertung/types.ts`  `erzeugung × CO2_FAKTOR_KG_KWH`
 *   • `v4/AuswertungenCo2V4.tsx`   `gesamtErzeugung × CO2_FAKTOR_KG_KWH`
 *
 * Beide rechneten auf der **Erzeugung** statt auf dem Eigenverbrauch, schrieben
 * also auch der eingespeisten kWh die volle Netzstrom-Vermeidung gut, und beide
 * kannten weder WP noch E-Mobilität. Ein Anwender sah dieselbe Größe zweimal
 * mit verschiedenen Zahlen. Beide sind mit N-21 auf `/cockpit/nachhaltigkeit`
 * umgestellt; dieser Wächter hält die Stelle frei.
 *
 * **Grenzen (am Code gemessen, keine Fußnote):**
 *  (a) Nur der benannte Faktor. Wer `0.38` hart hinschreibt, läuft daran vorbei
 *      — das fängt `check:design`/Review, nicht dieses Skript. Im Baum gibt es
 *      heute keine (gemessen 2026-07-31).
 *  (b) Kommentare werden gestrippt, Strings nicht. Ein Faktor in einem String
 *      wäre ohnehin keine Rechnung.
 *  (c) Der Wächter sagt nichts über die *Bezugsgröße* einer Backend-Zahl — nur
 *      darüber, dass der Client keine eigene bildet. Die Backend-Hälfte deckt
 *      `test_co2_tages_bezugsgroesse.py` (F-6) für den einen Pfad, der dort
 *      dieselbe Klasse trug; ein baumweiter Backend-Wächter fehlt noch (N-23).
 *  (d) Erkannt wird ein **Rechen-Operator unmittelbar vor oder nach** dem
 *      Faktor. Eine Rechnung, die den Faktor erst über eine neutral benannte
 *      Zwischenvariable einführt (`const f = CO2_FAKTOR_KG_KWH; e * f`), läuft
 *      vorbei — dieselbe Grenze wie beim Dienstlast-Wächter in ADR-001.
 *
 * **Wie diese Liste geprüft ist.** Der Wächter wurde gegen eine Probe-Datei in
 * beide Richtungen gemessen (2026-07-31): `e * FAKTOR` wird gefangen,
 * `FAKTOR * 1000` läuft durch, und — seit der Reihenfolge-Korrektur unten —
 * `e * FAKTOR * 1000` wird ebenfalls gefangen. Genau dieser Mischfall lief bis
 * dahin still durch, und die Grenzen-Liste erwähnte ihn nicht: die Freigabe für
 * die Einheiten-Umrechnung stieg aus, bevor der Operator DAVOR geprüft wurde.
 * Wer die Liste fortschreibt, misst neu — eine Grenze ohne Probe ist eine
 * Behauptung.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const FAKTOR = 'CO2_FAKTOR_KG_KWH'

/** Die EINE erlaubte Rechnung: kg/kWh → g/kWh für die Anzeige des Faktors. */
const EINHEITEN_UMRECHNUNG = /^\s*\*\s*1000\b/

/** Definition + Re-Export sind keine Verwendung. */
const DEFINITIONS_DATEIEN = new Set(['src/lib/constants.ts'])

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
const stripComments = (src) => src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')

/**
 * Import-Anweisungen entfernen — sie nennen den Faktor, verwenden ihn aber nicht.
 * Zeilenweise auszunehmen wäre die Falle: `export const x = (e) => e * FAKTOR`
 * beginnt ebenfalls mit einem Schlüsselwort und liefe an einer Zeilen-Heuristik
 * vorbei (gemessen beim Bau des Wächters — die erste Fassung tat genau das).
 * Der Zeilenumbruch bleibt erhalten, damit die Zeilennummern stimmen.
 */
const stripImports = (src) =>
  src.replace(/^import\s[\s\S]*?from\s*['"][^'"]+['"];?/gm,
    (treffer) => treffer.replace(/[^\n]/g, ' '))

/** Rechen-Operatoren, die aus dem Faktor eine abgeleitete Größe machen. */
const OPERATOR_DAVOR = /[*/+\-%]\s*$/
const VORKOMMEN = new RegExp(`\\b${FAKTOR}\\b`, 'g')

let geprueft = 0
const verstoesse = []

for (const f of quellDateien(join(ROOT, 'src'))) {
  const datei = rel(f)
  if (DEFINITIONS_DATEIEN.has(datei)) continue
  const src = stripImports(stripComments(readFileSync(f, 'utf8')))
  const zeilen = src.split('\n')
  let m
  VORKOMMEN.lastIndex = 0
  while ((m = VORKOMMEN.exec(src)) !== null) {
    geprueft++
    const danach = src.slice(m.index + FAKTOR.length)
    const davor = src.slice(0, m.index)
    const zeile = davor.split('\n').length
    const zeilenText = zeilen[zeile - 1] ?? ''

    // Reihenfolge ist hier die ganze Logik: erst prüfen, ob VOR dem Faktor
    // gerechnet wird, dann die Umrechnung freigeben. Andersherum (bis
    // 2026-07-31) lief `e * FAKTOR * 1000` durch — die Freigabe sah nur nach
    // rechts und stieg aus, bevor der Operator davor drankam.
    const operatorDavor = OPERATOR_DAVOR.test(davor)
    if (!operatorDavor && EINHEITEN_UMRECHNUNG.test(danach)) continue
    if (operatorDavor || /^\s*[*/+\-%]/.test(danach)) {
      verstoesse.push({ datei, zeile, text: zeilenText.trim() })
    }
  }
}

if (verstoesse.length) {
  for (const v of verstoesse) {
    console.error(`✗ CO₂-Menge im Client gerechnet: ${v.datei}:${v.zeile} — ${v.text}`)
  }
  console.error(
    `\ncheck:co2-roh — ${verstoesse.length} Abweichung(en).\n` +
    'CO₂-Mengen konstruiert ausschließlich das Backend (`berechne_co2_bilanz`, ' +
    'ADR-001/DI-2): Eigenverbrauch × Strommix + Wärmepumpe + E-Mobilität.\n' +
    'Der Client liest sie aus `/cockpit/nachhaltigkeit` — im Auswertungen-Sockel ' +
    'liegt sie als `basis.co2` bereit, in Cockpit/Jahr als `NachhaltigkeitMonat`.\n' +
    `Erlaubt bleibt allein die Anzeige des Faktors selbst (\`${FAKTOR} * 1000\` → g/kWh).`,
  )
  process.exit(1)
}

console.log(
  `✓ check:co2-roh — 0 CO₂-Rechnungen im Client (${geprueft} Vorkommen von ${FAKTOR} geprüft).`,
)
