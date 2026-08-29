#!/usr/bin/env node
/**
 * check-mobilkarte.mjs — die Mobil-Karte hat EINEN Bauort (N-149).
 *
 * Regel (KONZEPT-MOBILE §M3, Kanon „eine Datenliste, zwei Render-Pfade"): Passt
 * eine Tabelle unter `sm` nicht, kommt eine **Kartenliste derselben Daten** an
 * ihre Stelle. Der SoT dafür ist `components/ui/MobilKarte.tsx` — und nur er.
 *
 * ⭐ **Warum es diesen Wächter gibt.** N-149 ist genau dadurch entstanden, dass
 * das Muster VIERMAL im Baum stand: dreimal von Hand nachgebaut, einmal als
 * lokale Komponente in `PrognoseVergleichTeile.tsx`. Niemand hat das gemerkt,
 * weil jeder Nachbau für sich richtig aussah. Ohne Wächter entsteht der fünfte
 * genauso unbemerkt — der Fund nennt „die fünfte Stelle" wörtlich als Trigger.
 *
 * ⚑ **Was gemessen wird, und warum genau das.** Die Signatur ist der
 * **Container** der Kartenliste (`sm:hidden` + `space-y-2` in derselben
 * `className`), nicht die Karte selbst. Grund: ein einzelnes `rounded-lg border`
 * ist im Baum hundertfach berechtigt (jede Box), `sm:hidden` allein ebenfalls
 * (TKonto stapelt darunter Tabellen). **Erst die Kombination ist der Nachbau.**
 * Ein Prüfer, der auf `rounded-lg` anschlägt, meldet Rauschen und wird
 * abgeschaltet — das ist die teurere Fehlerart.
 *
 * ⛔ **Was er NICHT leistet, und das gehört dazu:** Er sieht die Zeichenkette.
 * Wer den Container mit `clsx('sm:hidden', 'space-y-2')` oder mit anderem
 * Abstand (`space-y-3`) baut, läuft durch. Er fängt den **wahrscheinlichen**
 * Nachbau — den per Copy-Paste aus einer der Bestandsstellen —, nicht jeden
 * denkbaren. Für die stärkere Form gäbe es nur einen AST-Lauf über
 * Tailwind-Klassenmengen; das steht in keinem Verhältnis zu einem P4-Befund.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SRC = join(ROOT, 'src')

/** Der einzige erlaubte Bauort — der SoT selbst. */
const SOT = 'src/components/ui/MobilKarte.tsx'

function tsxFiles(dir) {
  const out = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) out.push(...tsxFiles(p))
    else if (name.endsWith('.tsx') && !name.endsWith('.test.tsx')) out.push(p)
  }
  return out
}

function lineOf(src, index) {
  return src.slice(0, index).split('\n').length
}

/**
 * Container-Signatur der Kartenliste: eine `className`, die `sm:hidden` UND
 * `space-y-2` trägt — in beliebiger Reihenfolge, aber im selben Attribut.
 */
const CONTAINER = /className="[^"]*\bsm:hidden\b[^"]*\bspace-y-2\b[^"]*"|className="[^"]*\bspace-y-2\b[^"]*\bsm:hidden\b[^"]*"/g

const violations = []
let geprueft = 0

for (const file of tsxFiles(SRC)) {
  const rel = relative(ROOT, file)
  if (rel === SOT) continue
  geprueft++
  const src = readFileSync(file, 'utf8')
  let m
  while ((m = CONTAINER.exec(src)) !== null) {
    violations.push(`${rel}:${lineOf(src, m.index)}`)
  }
}

if (violations.length > 0) {
  console.error(
    `\n❌ check:mobilkarte — ${violations.length} handgebaute Mobil-Kartenliste(n) neben dem SoT:`,
  )
  for (const v of violations) console.error('  · ' + v)
  console.error(
    `\nFix: <MobilKarten> + <MobilKarte …> aus '${SOT}' verwenden ` +
      '(Regel 0a Fall 1 — der SoT ist da, er wird nur nicht angewandt). ' +
      'Fehlt der Karte eine Form, wird der SoT erweitert, nicht danebengebaut.',
  )
  process.exit(1)
}

console.log(
  `check:mobilkarte — ${geprueft} Dateien geprüft, die Mobil-Kartenliste hat genau einen Bauort.`,
)
console.log('✅ N-149: KONZEPT-MOBILE §M3 — eine Datenliste, zwei Render-Pfade, ein SoT.')
