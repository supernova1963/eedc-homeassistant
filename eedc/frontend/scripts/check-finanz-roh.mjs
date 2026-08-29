#!/usr/bin/env node
/**
 * check-finanz-roh.mjs — die Client-Hälfte der Wirtschaftlichkeitsrechnung (N-132/N-230).
 *
 * **Die Regel:** Der Client bildet **keine Amortisationsdauer**. Wo „Jahre"
 * angezeigt werden, steht eine Zahl aus einer Response — nicht ein Quotient,
 * den die Anzeige selbst gebildet hat.
 *
 * Warum es diesen Wächter gibt: Das Backend hat für die Dauer einen SoT
 * (`core/berechnungen/kapitalrechnung.py`) mit **zwei** Hälften, die nur
 * gemeinsam stimmen — Nenner ist der **Kapitaleinsatz** (relevante Kosten
 * + kumulierte sonstige Ausgaben − sonstige Erträge), Zähler die
 * annualisierte Ersparnis abzüglich gepflegter Betriebskosten. Ein Client, der
 * `Anschaffung ÷ Ersparnis` rechnet, lässt Alternativkosten, Förderung und
 * Betriebskosten weg und stellt seine Zahl neben die des ROI-Dashboards.
 * Genau das tat der Wallbox-Hub (`WallboxWirtschaftlichkeit.tsx:101`, N-230)
 * — eine geförderte Wallbox bekam dort eine zu lange Dauer.
 *
 * Das Backend-Gegenstück ist `test_berechnungs_layer_konformitaet.py` und, für
 * die Annahme-Zeile, `test_konzept_wirtschaftlichkeit_konformitaet.py`
 * (`test_schritt6_jede_dauer_nennt_ihre_annahme`). Im Frontend fehlte diese
 * Trennlinie als einziger der Kennzahl-Wächter — dieselbe Bauform wie
 * `check:co2-roh` (ADR-001/DI-2) und `check:kennwert-roh` (ADR-002/P3-a).
 *
 * **Warum am gerenderten Wort und nicht am Feldnamen — das ist die
 * Konstruktionsentscheidung.** Die naheliegende Fassung hätte
 * `anschaffungskosten_gesamt` als Divisions-Zähler gesucht. Sie hätte N-230
 * **nicht** gefangen: dort stand `const anschaffung = investition.
 * anschaffungskosten_gesamt` in Zeile 29 und die Division in Zeile 101, über
 * eine neutral benannte Zwischenvariable. Das ist wörtlich Grenze (d) von
 * `check:co2-roh` — ein Wächter, der beim zurückgebauten Fix grün bliebe, hat
 * nichts gemessen. Die Einheit dagegen steht immer unmittelbar beim Wert.
 *
 * **Grenzen (am Code gemessen, keine Fußnote):**
 *  (a) Nur die Einheit „Jahre". Eine Dauer in Monaten liefe vorbei; im Baum
 *      gibt es heute keine (gemessen 2026-08-29).
 *  (b) Nur eine Division im **Code-Anteil** derselben Zeile; Prosa in
 *      Template-Literalen und Strings wird nicht gelesen. Wer den
 *      Quotienten eine Zeile höher in eine Variable legt, läuft vorbei —
 *      dieselbe Grenze, die jeder dieser Wächter hat. Gegen die eine Bauform,
 *      die real vorkam (Feld → Variable → Division → Anzeige), hilft er
 *      trotzdem, weil die **Anzeige** die Division trug.
 *  (c) Der Amortisations-**Fortschritt** ist ausdrücklich NICHT Gegenstand.
 *      `RoiAnalyse.tsx` bildet `Ertrag ÷ Kapitaleinsatz × 100` und zeigt „%",
 *      nicht „Jahre": §4 des Konzepts sagt, der Fortschritt trifft **keine**
 *      Annahme über die Zukunft, die Dauer zwingend eine. Der Wächter zieht
 *      die Trennlinie deshalb an der Dauer.
 *
 * **Wie diese Liste geprüft ist.** Beidseitig gemessen (2026-08-29): mit dem
 * zurückgebauten N-230-Code (`${fmtZahl(anschaffung! / jahresErsparnis, 1)}
 * Jahre`) meldet der Wächter genau diese eine Stelle; ohne ihn meldet er 0 bei
 * 7 geprüften Anzeigen. Er sieht etwas UND er diskriminiert.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const EINHEIT = /\bJahre\b/

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
 * zeigt die Fundmeldung auf die falsche Stelle (N-165, dieselbe Fassung wie in
 * `check-co2-roh.mjs`/`check-datum-utc.mjs`).
 */
const stripComments = (src) =>
  src
    .replace(/\/\*[\s\S]*?\*\//g, (t) => t.replace(/[^\n]/g, ' '))
    .replace(/^[ \t]*\/\/.*$/gm, '')

/**
 * Den **Text** einer Zeile ausblenden und nur den Code stehen lassen: der
 * Prosa-Anteil eines Template-Literals (alles zwischen Backticks, was NICHT in
 * `${…}` steht) sowie einfache und doppelte Anführungszeichen. Länge und
 * Umbrüche bleiben erhalten, damit die Fundmeldung auf die richtige Stelle zeigt.
 *
 * ⚠ **Zwei Fassungen sind hier gescheitert, beide an derselben Zeile**
 * (`AuswertungenPrognoseV4.tsx:278`, „der SOLL/IST-Vergleich …"): die
 * zeilenweite Prüfung las den Schrägstrich der Prosa als Division, und die
 * Fassung „nur eingebettete Ausdrücke" half nicht, weil ein JSX-Attribut
 * (``text={`…`}``) das ganze Literal **samt** Prosa umschließt. Ein
 * Schrägstrich in einem Satz ist keine Rechnung — dieselbe Begründung, aus der
 * die Schwester-Wächter Kommentare strippen.
 */
function nurCode(zeile) {
  let out = ''
  let inBacktick = false
  let inExpr = 0
  let quote = null
  for (let i = 0; i < zeile.length; i++) {
    const c = zeile[i]
    if (quote) {
      out += c === quote ? c : ' '
      if (c === quote) quote = null
      continue
    }
    if (!inBacktick && (c === "'" || c === '"')) { quote = c; out += c; continue }
    if (c === '`' && !inExpr) { inBacktick = !inBacktick; out += ' '; continue }
    if (inBacktick && !inExpr) {
      if (c === '$' && zeile[i + 1] === '{') { inExpr = 1; out += '  '; i++; continue }
      out += ' '
      continue
    }
    if (inExpr) {
      if (c === '{') inExpr++
      else if (c === '}') { inExpr--; if (inExpr === 0) { out += ' '; continue } }
    }
    out += c
  }
  return out
}

/**
 * Division erkennen, JSX-Syntax ausnehmen: `</div>`, `<br />`, `//`, `/*`.
 * Verlangt links einen Wert: Bezeichner, Ziffer, `)`, `]` — **oder `!`**.
 *
 * ⛔ **Das `!` ist nicht Kosmetik, es war ein falsch-NEGATIVER Wächter.** Ohne
 * es meldete dieser Prüfer den zurückgebauten N-230-Code
 * (`anschaffung! / jahresErsparnis`) **nicht**: links vom Operator stand die
 * Non-Null-Assertion, kein Wortcharakter. Er war grün, obwohl der Defekt
 * dastand — und dieselbe Bauform hätte er im nächsten Fall wieder
 * durchgelassen. Aufgefallen ist es allein an der beidseitigen Gegenprobe;
 * drei Fassungen dieses Skripts sind an je einer Zeile gescheitert (zweimal
 * falsch-positiv an Prosa, einmal hier falsch-negativ).
 * *Ein Wächter, der bei zurückgebautem Fix grün bleibt, hat nichts gemessen.*
 */
const DIVISION = /[\w)\]!]\s*\/(?![/>*])/

let geprueft = 0
const verstoesse = []

for (const f of quellDateien(join(ROOT, 'src'))) {
  const datei = rel(f)
  const zeilen = stripComments(readFileSync(f, 'utf8')).split('\n')
  zeilen.forEach((roh, i) => {
    if (!EINHEIT.test(roh)) return
    geprueft++
    if (DIVISION.test(nurCode(roh))) {
      verstoesse.push({ datei, zeile: i + 1, text: roh.trim() })
    }
  })
}

if (verstoesse.length) {
  for (const v of verstoesse) {
    console.error(`✗ Amortisationsdauer im Client gerechnet: ${v.datei}:${v.zeile} — ${v.text}`)
  }
  console.error(
    `\ncheck:finanz-roh — ${verstoesse.length} Abweichung(en).\n` +
    `Die Dauer kommt aus dem Backend-SoT (kapitalrechnung.py): Kapitaleinsatz ÷\n` +
    `Jahres-Ersparnis, dazu der Annahme-Text aus derselben Antwort. Der Client\n` +
    `zeigt sie an, er bildet sie nicht.`
  )
  process.exit(1)
}

console.log(`check:finanz-roh — 0 Abweichungen (${geprueft} Zeilen mit „Jahre" geprüft).`)
