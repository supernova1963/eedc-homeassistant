#!/usr/bin/env node
/**
 * check-datum-utc.mjs — ein Datums-Key kommt aus der LOKALEN Uhr, nie aus UTC (F-5).
 *
 * **Die Regel:** Wer aus einer Uhr einen ISO-Datums-Key (`'2026-08-06'`) bildet,
 * nimmt `heuteIso()` / `toIsoDatum()` / `verschiebeIsoTage()` aus `src/lib/datum.ts`.
 * `new Date().toISOString().slice(0, 10)` (und die Geschwister `.split('T')[0]`,
 * `.substring(0, 10)`) sind verboten — `toISOString()` serialisiert in **UTC**.
 *
 * **Warum, und warum erst jetzt.** In Mitteleuropa ist das UTC-Datum zwischen
 * 00:00 und 02:00 Ortszeit (Sommerzeit; im Winter 00:00–01:00) noch **gestern**,
 * während das Backend mit `date.today()` in der Container-Zeitzone rechnet. Zwei
 * Stunden pro Nacht rechnen Client und Server also über verschiedene Tage.
 * Tagsüber ist alles unauffällig — genau deshalb ist es 2026 lange unbemerkt
 * geblieben und wurde nur durch eine Anwender-Meldung sichtbar (rapahl,
 * 06.08.2026, mit Screenshots um 00:40 und 01:15 Uhr):
 *
 *   Der Prognosen-Vergleich zeigte **zwei Kalendertage mit identischen Werten in
 *   allen drei Quellenspalten**. Die „heute"-Zeile trug das UTC-Datum von
 *   gestern, aber die Backend-Werte von heute; die Zukunftsliste (Filter
 *   `datum > heute`) lieferte denselben Tag gleich noch einmal. Und weil die
 *   Wetter-Ikone per `find(om.datum === heute)` in einer Liste gesucht wurde,
 *   die erst bei heute beginnt, blieb sie in der Doppelzeile leer — das war der
 *   Beleg, dass es kein Datenzufall war.
 *
 * Beim Aufräumen waren es **zehn** Fundstellen mit echter Wirkung, nicht eine:
 * unter anderem reaggregierte der Knopf „Tag neu berechnen" nachts **gestern**,
 * die Tages-Rail markierte den Vortag als „heute", eine zum heutigen Tag
 * stillgelegte Komponente galt noch als aktiv, und ein heute beginnender
 * Stromtarif galt noch nicht.
 *
 * **Klassifizierte Ausnahmen** (unten `ERLAUBT`): Stellen, an denen der Tag
 * kippen darf, weil aus ihm kein Vergleich und keine Abfrage wird — ein Datum im
 * **Dateinamen** eines Downloads, und die **Vorbelegung** eines Formularfelds,
 * die der Anwender sieht und ändern kann. Beide sind bewusst nicht mitgebaut
 * worden: sie sind kein Fehler, und wer sie mitnimmt, weitet den Auftrag über
 * den gemessenen Schaden hinaus aus. Wird eine solche Stelle einmal zu einem
 * Vergleich, fliegt sie aus der Liste.
 *
 * **Grenzen (gemessen, keine Fußnote):**
 *  (a) Erkannt wird der Aufruf auf einem `Date`. Wer sich das Datum über
 *      `Intl.DateTimeFormat` mit `timeZone: 'UTC'` baut, läuft vorbei — im Baum
 *      gibt es das heute nicht (gemessen 2026-08-06, `grep timeZone` → 0).
 *  (b) `toISOString()` ohne anschließendes Abschneiden ist erlaubt: ein voller
 *      Zeitstempel trägt seine Zone mit und ist unmissverständlich.
 *  (c) Kommentare werden gestrippt — sonst meldete diese Datei sich selbst und
 *      der Erklärtext in `lib/datum.ts`.
 *
 * **Wie das geprüft ist.** Gegen eine Probe in beide Richtungen gemessen
 * (2026-08-06): `new Date().toISOString().slice(0, 10)` wird gefangen,
 * `d.toISOString()` ohne Schnitt läuft durch, und eine neue Datei mit dem
 * Muster wird gefangen, auch wenn sie nicht in `ERLAUBT` steht. Wer die
 * Grenzen-Liste fortschreibt, misst neu — eine Grenze ohne Probe ist eine
 * Behauptung.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')

/** Der SoT selbst — er erklärt das Muster und darf es nennen. */
const SOT_DATEIEN = new Set(['src/lib/datum.ts'])

/**
 * Erlaubt, weil aus dem Datum kein Vergleich und keine Abfrage wird.
 * Jede Zeile trägt ihren Grund; ohne Grund kein Eintrag.
 */
const ERLAUBT = new Map([
  ['src/components/ui/DestructiveActionDialog.tsx', 'Datum im Dateinamen des Sicherungs-Downloads'],
  ['src/pages/AnlagenTeile.tsx', 'Datum im Dateinamen des Anlagen-Exports'],
  ['src/pages/BackupTeile.tsx', 'Datum im Dateinamen des Backups'],
  ['src/pages/ProtokolleTeile.tsx', 'Datum im Dateinamen des Log-Downloads'],
  ['src/components/setup-wizard/steps/StrompreiseStep.tsx', 'Vorbelegung „gültig ab" — sichtbar und änderbar'],
  ['src/hooks/useSetupWizard.ts', 'Vorbelegung „gültig ab" — sichtbar und änderbar'],
])

/**
 * Zusätzlich erlaubt für Dateien, die BEIDES tun (Vorbelegung + Vergleich) —
 * angeheftet an den **Inhalt** der Zeile, nicht an ihre Nummer.
 *
 * ⚑ **Warum der Umbau (N-195 · N-263, Entscheid Gernot 23.08.2026).** Bis dahin
 * stand hier eine Zeilennummer, und sie musste **viermal** nachgeführt werden —
 * 08.08. (vier Kommentarzeilen darüber), 17.08. (N-257: die benannte Regel
 * `erstTarifVorbelegung`), 22.08. (#392: ein Import), zuletzt 549 → 575 → 576.
 * Jede Einfügung *irgendwo darüber* macht den Eintrag falsch-rot; der Prüfer
 * meldet das zwar laut, aber die Meldung ist jedes Mal ein Fehlalarm, und ein
 * Prüfer, der regelmäßig grundlos rot wird, wird irgendwann weggeklickt.
 *
 * ⚠ **Der Einwand gegen den Inhalts-Anker war: er erlaubt dieselbe Zeile
 * ungewollt MEHRFACH.** Deshalb steht neben jedem Anker eine **Anzahl**. Taucht
 * der Ausschnitt öfter auf als freigegeben, wird der Prüfer rot — die neue
 * Kopie ist dann eben nicht mitfreigegeben. Taucht er seltener auf, wird er
 * **auch** rot: die Stelle ist umgebaut oder weg, und der Eintrag gehört
 * angepasst statt vergessen. (Dieselbe Mechanik trägt seit dem 23.08. die
 * Baseline von `backend/tests/test_konformitaet_echte_uhr_in_tests.py`.)
 *
 * Der Schlüssel ist der **Whitespace-normalisierte** Quelltext der Zeile
 * (Kommentare sind zu diesem Zeitpunkt schon gestrippt). Prettier darf also
 * umbrechen und einrücken; wird die Zeile inhaltlich geändert, fällt die
 * Freigabe — und genau das soll sie.
 */
const ERLAUBT_STELLEN = new Map([
  ['src/pages/StrompreiseTeile.tsx', new Map([
    // istGueltigHeute() darüber ist umgestellt; hier geht es um das
    // Formular-Default „gültig ab", das der Anwender sieht und ändern kann.
    [
      "gueltig_ab: strompreis?.gueltig_ab || gueltigAbVorbelegung || new Date().toISOString().split('T')[0],",
      1,
    ],
  ])],
])

/** Whitespace kollabieren — der Anker soll Umbrüche und Einrückung überleben. */
const normalisiere = (s) => s.trim().replace(/\s+/g, ' ')

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

/**
 * Kommentare neutralisieren, **ohne eine einzige Zeile zu verlieren** — sonst
 * zeigt die Fundmeldung auf die falsche Stelle.
 *
 * Zwei Fallen, beide beim Bau gemessen (2026-08-06): ein Block-Kommentar darf
 * nicht ersatzlos gelöscht werden (seine Umbrüche fehlen dann), und die
 * Zeilen-Kommentar-Regex darf **nicht** mit `\s*` beginnen — `\s` schließt
 * `\n` ein und verschluckt den Umbruch der Vorzeile. Die erste Fassung tat
 * beides und meldete 534 statt 545, also 15 Zeilen daneben.
 */
const stripComments = (src) =>
  src
    .replace(/\/\*[\s\S]*?\*\//g, (t) => t.replace(/[^\n]/g, ' '))
    .replace(/^[ \t]*\/\/.*$/gm, '')

/** `toISOString()` gefolgt vom Abschneiden auf das Datum — in irgendeiner Form. */
const MUSTER = /toISOString\(\)\s*\.\s*(?:slice\(\s*0\s*,\s*10\s*\)|substring\(\s*0\s*,\s*10\s*\)|split\(\s*['"]T['"]\s*\)\s*\[\s*0\s*\])/g

let geprueft = 0
let freigegeben = 0
const verstoesse = []
/** `datei → anker → wie oft tatsächlich getroffen` (gegen die Anzahl geprüft). */
const ankerTreffer = new Map()

for (const f of quellDateien(join(ROOT, 'src'))) {
  const datei = rel(f)
  if (SOT_DATEIEN.has(datei)) continue
  const src = stripComments(readFileSync(f, 'utf8'))
  const zeilen = src.split('\n')
  let m
  MUSTER.lastIndex = 0
  while ((m = MUSTER.exec(src)) !== null) {
    geprueft++
    const zeile = src.slice(0, m.index).split('\n').length
    const text = normalisiere(zeilen[zeile - 1] ?? '')
    if (ERLAUBT.has(datei)) { freigegeben++; continue }
    const anker = ERLAUBT_STELLEN.get(datei)
    if (anker?.has(text)) {
      const je = ankerTreffer.get(datei) ?? new Map()
      je.set(text, (je.get(text) ?? 0) + 1)
      ankerTreffer.set(datei, je)
      continue // Zählung entscheidet unten, ob das eine Freigabe bleibt
    }
    verstoesse.push({ datei, zeile, text })
  }
}

// Anzahl gegen Freigabe — in BEIDE Richtungen. Zu viele Treffer heißt: eine
// Kopie hat sich unter die Freigabe gestellt. Zu wenige heißt: die freigegebene
// Stelle gibt es so nicht mehr, der Eintrag ist verwaist (dieselbe
// Abschmelz-Regel wie bei den Backend-Baselines).
const ankerFehler = []
for (const [datei, anker] of ERLAUBT_STELLEN) {
  for (const [text, erwartet] of anker) {
    const ist = ankerTreffer.get(datei)?.get(text) ?? 0
    if (ist === erwartet) { freigegeben += ist; continue }
    ankerFehler.push(
      ist > erwartet
        ? `  ${datei}  ${ist}× statt ${erwartet}× freigegeben — eine KOPIE dieser Zeile ` +
          `hat sich unter die Freigabe gestellt:\n      ${text}`
        : `  ${datei}  nur ${ist}× statt ${erwartet}× gefunden — die freigegebene Stelle ` +
          `gibt es so nicht mehr. Eintrag anpassen oder streichen:\n      ${text}`,
    )
  }
}

if (ankerFehler.length) {
  console.error(ankerFehler.join('\n'))
  console.error(
    `\n✗ check:datum-utc — die Freigabe-Anker stimmen nicht mehr mit dem Code überein.\n` +
    `  Der Anker ist der Zeileninhalt (Whitespace-normalisiert), die Zahl daneben sagt,\n` +
    `  wie oft er vorkommen darf. Beide Richtungen sind Absicht: eine neue Kopie ist NICHT\n` +
    `  mitfreigegeben, und eine verschwundene Stelle darf keinen toten Eintrag hinterlassen.`,
  )
  process.exit(1)
}

if (verstoesse.length) {
  for (const v of verstoesse) {
    console.error(`  ${v.datei}:${v.zeile}  ${v.text}`)
  }
  console.error(
    `\n✗ check:datum-utc — ${verstoesse.length} Datums-Key(s) aus UTC statt aus der lokalen Uhr.\n` +
    `  toISOString() serialisiert in UTC: zwischen 00:00 und 02:00 Ortszeit ist das noch gestern,\n` +
    `  während das Backend mit date.today() rechnet (F-5, gemeldet von rapahl 06.08.2026).\n` +
    `  Nimm heuteIso() / toIsoDatum() / verschiebeIsoTage() aus src/lib/datum.ts.\n` +
    `  Wird aus dem Datum nachweislich kein Vergleich (Dateiname, sichtbare Vorbelegung),\n` +
    `  gehört die Stelle mit Begründung in die ERLAUBT-Liste dieses Skripts.`,
  )
  process.exit(1)
}

console.log(
  `✓ check:datum-utc — 0 UTC-Datums-Keys (${geprueft} Vorkommen geprüft, ${freigegeben} klassifiziert freigegeben).`,
)
