#!/usr/bin/env node
/**
 * check-formel-herleitung.mjs — Wächter des Style-Guide-Prinzips **A6**
 * („Berechnungs-Transparenz", `docs/KONZEPT-STYLE-GUIDE.md`).
 *
 * Die Regel: Wer eine abgeleitete Kennzahl anzeigt, zeigt daneben **Formel +
 * eingesetzte Werte**. Eine Zahl, die ihre Eingangsgrößen nicht nennt, lässt
 * sich nicht einordnen — und wo zwei Größen dieselbe Einheit tragen, fällt eine
 * falsche Zuordnung dann gar nicht auf. Genau das ist am 01.09.2026 eingetreten:
 * ein Melder sah über Monate Arbeitszahlen von 0,7 und konnte die Ursache nicht
 * sehen, weil die Kachel nur „JAZ = Wärme ÷ Strom" sagte (Fund N-365).
 * A6 gab es seit dem Style-Guide — **maschinell geprüft wurde sie nie**.
 *
 * ── Bauform: TypeScript-Syntaxbaum, nicht Rohtext ────────────────────────────
 *
 * Ob `formel` und `berechnung` **im selben Objekt** stehen, ist eine Baumfrage.
 * Ein Zeichenfenster (so hat die Erhebung vom 01.09. gemessen) beantwortet sie
 * nur zufällig richtig, und eine Klammer-Balance auf Rohtext scheitert real an
 * `formel: string` in einer **Parameterliste** (`v4/komponentenAdapter.tsx`,
 * Helfer `jazJeFunktion`). ⭐ Und eine Textsuche nach `formel:` ist gegenüber
 * der **Shorthand**-Form `{ formel }` dauerhaft blind — genau so sind drei
 * Kacheln (JAZ Heizen/Warmwasser/Kühlen) durch jede Erhebung gefallen, bis der
 * Baum sie am 13.09.2026 gezeigt hat.
 *
 * ── Gegenstand: ZWEI Trägerformen ────────────────────────────────────────────
 *
 *   (1) Objektliteral mit der Eigenschaft `formel` (auch Shorthand), deren Wert
 *       nicht literal `null`/`undefined` ist — die Kachel-Form (`KpiStripItem`,
 *       `TKontoPosten`, `SensorExportItem`).
 *   (2) JSX-Attribut `formel=` an `<FormelTooltip>`/`<KPICard>`/`<BilanzKachel>`
 *       — **außer** reinem Durchreichen (`formel={formel}`, `formel={k.formel}`).
 *       `formel={ERGEBNIS_FORMEL}` ist KEIN Durchreichen: eine Konstante ist ein
 *       Formeltext, nur an anderer Stelle geschrieben.
 *
 * **Wertsensibel, in beide Richtungen** (am Baum gemessen, nicht angenommen):
 *   · `formel: null` ist **kein** Gegenstand — `v4/JahrAggregat.tsx` setzt es
 *     absichtlich (ein Jahres-Σ hat kein Monats-Formelbild).
 *   · `berechnung: null` **erfüllt nicht** — `pages/HAExportSettingsTeile.tsx`
 *     setzt es A3-korrekt für einen Sensor ohne Wert; das ist eine Ausnahme mit
 *     Begründung, kein erfüllter Fall.
 *   · Typdeklarationen (`formel: string` in Interface/Type/Parameterliste) sind
 *     keine Objektliterale und fallen von selbst heraus.
 *
 * ── Drei Prüfungen, alle drei rot-fähig ──────────────────────────────────────
 *
 *   P1  Träger ohne `berechnung` und ohne Allowlist-Eintrag  ⇒ rot
 *   P2  Allowlist-Eintrag ohne `klasse` ∈ {a,b,c} oder mit `grund` < 20 Zeichen ⇒ rot
 *   P3  Allowlist-Eintrag **ohne Gegenstand** (Marke gibt es nicht mehr, oder sie
 *       trägt inzwischen ein `berechnung`) ⇒ rot — abschmelzend, Mechanik
 *       wörtlich von `src/test/check-einhaengung.test.ts` (2. `it`). Ohne sie
 *       deckt ein toter Eintrag später eine neue Lücke zu; genau so hat
 *       `EXPECTED_ROUTES = 217` gegen 271 reale Routen nichts mehr gemessen.
 *
 * ── Die drei Ausnahmeklassen (A6-Nachtrag 13.09.2026, Entscheid Gernot) ──────
 *
 *   a  Herkunftsangabe · roher Zähler · triviale Σ mit sichtbaren Summanden
 *   b  Quotient/Differenz, deren Eingangswerte als eigene Kacheln, in der
 *      Zweitzeile derselben Kachel oder in der Kopfzeile desselben Blocks stehen
 *
 * ⛔ **Es gibt keine dritte Klasse „dokumentiert offen".** Sie stand hier einen
 * halben Tag lang, für die drei Arbeitszahlen je Funktion im Komponenten-Hub,
 * deren Eingangswerte die Antwort damals nicht enthielt. Entscheid Gernot
 * (13.09.2026): *ein benannter Deckel ist ein Deckel* — der Fund N-365 verlangt
 * ausdrücklich keinen. Die drei Kacheln haben ihre Herleitung stattdessen
 * bekommen (sechs Felder in der WP-Zusammenfassung). Wer künftig vor derselben
 * Lage steht, ergänzt das fehlende Feld im Backend, statt eine Klasse zu öffnen.
 *
 * ── Grenzen, benannt statt als Fußnote ───────────────────────────────────────
 *
 *  (a) Er prüft **Präsenz**, nicht **Aussagekraft**. `berechnung: 'je Lade-
 *      Entlade-Zyklus einzeln, danach summiert'` (`v4/SpeicherPotentialIST.tsx`)
 *      und `berechnung={ERGEBNIS_ABGRENZUNG}` (`finanzen/TKonto.tsx`) sind Prosa
 *      und gelten ihm als erfüllt. Gemessen 13.09.2026: 3 von 56.
 *  (b) Er sieht keine **Render-Geometrie**. Ob die Nachbarkachel, auf die eine
 *      (b)-Begründung zeigt, tatsächlich erscheint — oder geparkt ist —, kann er
 *      nicht wissen. Der Park-Vorbehalt steht deshalb im A6-Text selbst.
 *  (c) Er folgt keiner **Variablen**. Steht der Formeltext in einer Konstanten
 *      außerhalb des Objekts, sieht er die Stelle, nicht den Text.
 */
import { readdirSync, readFileSync, statSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SRC = join(ROOT, 'src')
const ALLOWLIST_PFAD = join(ROOT, 'scripts', 'formel-herleitung-allowlist.json')
const ALLOWLIST = existsSync(ALLOWLIST_PFAD)
  ? JSON.parse(readFileSync(ALLOWLIST_PFAD, 'utf8'))
  : {}
const KLASSEN = new Set(['a', 'b'])
const GRUND_MIN = 20

/** Alle Quelldateien ohne Proben und ohne reine Typdateien. */
function dateien(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) dateien(p, out)
    else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) && !/\.d\.ts$/.test(name)) out.push(p)
  }
  return out
}

const istNullish = (n) =>
  !n || n.kind === ts.SyntaxKind.NullKeyword || (ts.isIdentifier(n) && n.text === 'undefined')

/** Statischer Text eines Ausdrucks — Template-Platzhalter werden zu `…`. */
function statischerText(n, sf) {
  if (!n) return null
  if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) return n.text.trim()
  if (ts.isTemplateExpression(n)) {
    const teile = [n.head.text, ...n.templateSpans.map((s) => s.literal.text)]
    const t = teile.join('…').replace(/\s+/g, ' ').trim()
    return t.replace(/^…+/, '…').replace(/…+$/, '…') || null
  }
  if (ts.isJsxExpression(n)) return statischerText(n.expression, sf)
  return null
}

const NAMENS_SCHLUESSEL = ['title', 'label', 'titel', 'name']

/** Name der nächsten umschließenden Deklaration — die Rückfallmarke, wenn eine
 *  Kachel weder Titel noch Text-Argument trägt (Shorthand `{ formel }` in einem
 *  Helfer, Objekt aus einem `map`). Stabiler als eine Zeilennummer. */
function umschliessenderName(n, sf) {
  let k = n.parent
  while (k) {
    if (ts.isVariableDeclaration(k) && ts.isIdentifier(k.name)) return k.name.text
    if ((ts.isFunctionDeclaration(k) || ts.isMethodDeclaration(k)) && k.name && ts.isIdentifier(k.name)) return k.name.text
    k = k.parent
  }
  return null
}

/** Rückfallmarke: umschließende Deklaration + Quelltext des Formel-Ausdrucks. */
function rueckfallMarke(knoten, wert, rel, sf) {
  const ft = statischerText(wert, sf)
  const kern = ft ?? wert.getText(sf).replace(/\s+/g, ' ').slice(0, 60)
  const um = umschliessenderName(knoten, sf)
  return `${rel}::${um ? `${um}/` : ''}formel:${kern}`
}

/** Marke = `<Pfad>::<Bezeichner>` — NICHT die Zeilennummer (die rotiert bei
 *  jedem Umbau; die Lehre `EXPECTED_ROUTES = 217` steht in check-einhaengung). */
function markeFuerObjekt(obj, formelInit, rel, sf) {
  for (const key of NAMENS_SCHLUESSEL) {
    const p = obj.properties.find(
      (x) => ts.isPropertyAssignment(x) && x.name && ts.isIdentifier(x.name) && x.name.text === key,
    )
    const t = p ? statischerText(p.initializer, sf) : null
    if (t) return `${rel}::${t}`
  }
  // Options-Objekt eines Aufrufs (`k('Zyklen/Monat', …, { formel })`) — der Name
  // steht dann im ersten Text-Argument, nicht im Objekt.
  let auf = obj.parent
  while (auf && !ts.isCallExpression(auf) && !ts.isReturnStatement(auf)) auf = auf.parent
  if (auf && ts.isCallExpression(auf)) {
    for (const arg of auf.arguments) {
      const t = statischerText(arg, sf)
      if (t) return `${rel}::${t}`
    }
  }
  return rueckfallMarke(obj, formelInit, rel, sf)
}

function markeFuerJsx(el, wert, rel, sf) {
  const attrs = el.attributes.properties
  const titel = attrs.find(
    (a) => ts.isJsxAttribute(a) && a.name && ts.isIdentifier(a.name) && NAMENS_SCHLUESSEL.includes(a.name.text),
  )
  const t = titel ? statischerText(titel.initializer, sf) : null
  if (t) return `${rel}::${t}`
  // Kinder eines <FormelTooltip>Performance Ratio</FormelTooltip>
  const eltern = el.parent
  if (eltern && ts.isJsxElement(eltern)) {
    const kind = eltern.children.map((c) => (ts.isJsxText(c) ? c.text : '')).join('').trim()
    if (kind) return `${rel}::${kind.replace(/\s+/g, ' ')}`
  }
  return rueckfallMarke(el, wert, rel, sf)
}

/** Ist der JSX-Wert reines Durchreichen (`{formel}` / `{k.formel}`)? */
function istDurchreichung(n) {
  if (ts.isIdentifier(n)) return n.text === 'formel'
  if (ts.isPropertyAccessExpression(n)) return n.name.text === 'formel'
  return false
}

const traeger = []
for (const datei of dateien(SRC)) {
  const text = readFileSync(datei, 'utf8')
  const sf = ts.createSourceFile(datei, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const rel = datei.slice(ROOT.length + 1)
  const zeile = (n) => sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1

  const geh = (node) => {
    if (ts.isObjectLiteralExpression(node)) {
      const prop = (name) =>
        node.properties.find(
          (p) => (ts.isPropertyAssignment(p) || ts.isShorthandPropertyAssignment(p))
            && p.name && ts.isIdentifier(p.name) && p.name.text === name,
        )
      const fp = prop('formel')
      if (fp) {
        const init = ts.isPropertyAssignment(fp) ? fp.initializer : fp.name
        if (!istNullish(init)) {
          // `eingesetzte_werte` ist dieselbe Aussage in strukturierter Form: die Herleitung der Ergebnis-Leiter
          // (`ErgebnisStufe`, Backend `core/berechnungen/ergebnis.py`, 03.10.2026) trägt Formel UND die Liste der
          // eingesetzten Werte; der Anzeigetext entsteht daraus erst beim Formatieren (`lib/ergebnisHerleitung.ts`).
          const bp = prop('berechnung') ?? prop('eingesetzte_werte')
          const binit = bp ? (ts.isPropertyAssignment(bp) ? bp.initializer : bp.name) : null
          traeger.push({
            marke: markeFuerObjekt(node, init, rel, sf),
            datei: rel, zeile: zeile(fp), form: 'Objekt',
            erfuellt: !!bp && !istNullish(binit),
          })
        }
      }
    }
    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const attr = (name) => node.attributes.properties.find(
        (a) => ts.isJsxAttribute(a) && a.name && ts.isIdentifier(a.name) && a.name.text === name,
      )
      const fa = attr('formel')
      if (fa && fa.initializer) {
        const wert = ts.isJsxExpression(fa.initializer) ? fa.initializer.expression : fa.initializer
        if (wert && !istNullish(wert) && !istDurchreichung(wert)) {
          const ba = attr('berechnung')
          const bwert = ba && ba.initializer
            ? (ts.isJsxExpression(ba.initializer) ? ba.initializer.expression : ba.initializer)
            : null
          traeger.push({
            marke: markeFuerJsx(node, wert, rel, sf),
            datei: rel, zeile: zeile(node), form: 'JSX',
            erfuellt: !!ba && !istNullish(bwert),
          })
        }
      }
    }
    ts.forEachChild(node, geh)
  }
  geh(sf)
}

const fehler = []

// P1 — Träger ohne Herleitung und ohne Ausnahme.
const ungedeckt = traeger.filter((t) => !t.erfuellt && !(t.marke in ALLOWLIST))
for (const t of ungedeckt) {
  fehler.push(`[P1] ${t.datei}:${t.zeile} (${t.form}) — Formel ohne eingesetzte Werte\n        Marke: ${t.marke}`)
}

// P2 — Ausnahme ohne belastbare Begründung.
for (const [marke, e] of Object.entries(ALLOWLIST)) {
  const klasse = e && typeof e === 'object' ? e.klasse : undefined
  const grund = e && typeof e === 'object' ? e.grund : undefined
  if (!KLASSEN.has(klasse)) {
    fehler.push(`[P2] ${marke} — Klasse ${JSON.stringify(klasse)} unzulässig (erlaubt: a, b)`)
  }
  if (typeof grund !== 'string' || grund.trim().length < GRUND_MIN) {
    fehler.push(`[P2] ${marke} — Begründung fehlt oder ist kürzer als ${GRUND_MIN} Zeichen`)
  }
}

// P3 — Ausnahme ohne Gegenstand (abschmelzend).
const offeneMarken = new Set(traeger.filter((t) => !t.erfuellt).map((t) => t.marke))
for (const marke of Object.keys(ALLOWLIST)) {
  if (!offeneMarken.has(marke)) {
    const existiert = traeger.some((t) => t.marke === marke)
    fehler.push(
      `[P3] ${marke} — Ausnahme ohne Gegenstand (${existiert ? 'trägt inzwischen eine Berechnung' : 'Marke gibt es nicht mehr'}); Eintrag streichen`,
    )
  }
}

if (fehler.length > 0) {
  console.error('\ncheck:formel-herleitung — A6 verletzt:\n')
  for (const f of fehler) console.error(`  ✗ ${f}`)
  console.error(
    '\nA6: Wer eine abgeleitete Kennzahl zeigt, zeigt daneben Formel UND eingesetzte Werte.\n' +
    'Die Werte kommen aus DERSELBEN Antwort wie der Wert daneben — nicht aus einer\n' +
    'Client-Rechnung; sonst führt die Herleitung auf eine andere Zahl als die Kachel.\n' +
    'Fehlt ein Eingangswert in der Antwort: Backend-Feld ergänzen, nicht schätzen.\n' +
    'Begründete Ausnahme → scripts/formel-herleitung-allowlist.json\n' +
    '  { "<pfad>::<Kachelname>": { "klasse": "a"|"b", "grund": "…" } }\n' +
    '  a = Herkunftsangabe / roher Zähler / triviale Σ mit sichtbaren Summanden\n' +
    '  b = Quotient, dessen Eingangswerte auf derselben Fläche stehen\n' +
    '⛔ Es gibt keine Klasse für „offen, aber bekannt" — wer sie bräuchte, baut das\n' +
    '   fehlende Backend-Feld (Entscheid Gernot 13.09.2026, s. Kopfkommentar).\n',
  )
  process.exit(1)
}

const zaehle = (k) => Object.values(ALLOWLIST).filter((e) => e.klasse === k).length
console.log(
  `\ncheck:formel-herleitung — ${traeger.length} Formel-Träger geprüft ` +
  `(${traeger.filter((t) => t.form === 'Objekt').length} Objekt · ${traeger.filter((t) => t.form === 'JSX').length} JSX) · ` +
  `${traeger.filter((t) => t.erfuellt).length} mit Herleitung · ` +
  `${Object.keys(ALLOWLIST).length} als A6-Ausnahme geführt (a: ${zaehle('a')} · b: ${zaehle('b')}) · ` +
  `0 ungedeckt.`,
)
console.log('✅ Jede angezeigte Formel nennt ihre eingesetzten Werte oder ist begründete Ausnahme.')
