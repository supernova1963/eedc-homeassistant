#!/usr/bin/env node
/**
 * check-park-gate.mjs — Wächter der Element-Park-Doktrin, Hälfte 3: das AUTO-HIDE-GATE.
 *
 * Doktrin (Gernot 2026-06-27 / 07-09): Jede Anzeige ist einzeln parkbar — und **ein Block
 * verschwindet, wenn ALLE seine Elemente geparkt sind**. Die erste Hälfte prüft
 * `check:parkbar` (Atomarität), die zweite `check:parkbar-vollstaendig` (jede Anzeige IST
 * parkbar). Die dritte, das Gate selbst, hatte bis zum 2026-09-06 **keinen Quelltext-Wächter**:
 * sie hing allein am `check:park-leertest`, einem Playwright-Livetest gegen eine laufende
 * Demo-Box (188 s, kein CI-Lauf, nur am Auslöser).
 *
 * ⛔ **Warum der Livetest abgelöst wurde und nicht repariert:** Er meldete am 2026-09-06 GRÜN
 * über ein Park-Element, das er nie gesehen hat (`komp-wp-chart-bauart` auf
 * `#/community/komponenten` — eine Sicht, die in seiner `ROUTES`-Liste fehlte). Gemessen:
 * er besuchte EINE der sechs Community-Sichten, während 12 der 17 Auto-Hide-Dateien dort
 * liegen. *Er vermied eine gepflegte ID-Liste und pflegte dafür eine Routen-Liste — dieselbe
 * Drift, eine Ebene höher.* Entscheid Gernot: ersetzen, nicht reparieren.
 *
 * ── Was dieser Wächter prüft ──────────────────────────────────────────────────────────
 *
 *  R1 · BLOCK-GATE — Ein Block-Objektliteral (`{ id, title, render }`, wie {@link BlockShell}
 *       sie erwartet), dessen `render` Park-Elemente erzeugt, muss GEGATED eingehängt sein.
 *       Sonst bleibt der Block leer-aber-sichtbar stehen, wenn der Anwender alles darin parkt.
 *
 *  R2 · HÜLLEN-GATE — Eine `<FokusKachel>`, deren Kinder Park-Elemente erzeugen, muss
 *       entweder selbst in einer `<Parkbar>` stecken (dann verschwindet sie mit ihr) ODER
 *       ihre Funktion trägt einen Park-Früh-Return. Das ist die dritte Klasse aus dem
 *       Fehlertext des Livetests: „Container-Hülle versteckt sich nicht bei Voll-Park".
 *
 * ── Die drei Gate-Formen, die der Baum benutzt (2026-09-06 erhoben, nicht angenommen) ──
 *
 *   (a) Bedingung im Array:   `...(sichtbar(ids) ? [block] : [])` · `cond && !alleGeparkt(x) ? {…} : null`
 *   (b) Bedingtes Anhängen:   `if (!alleGeparkt(ids)) bloecke.push({…})`
 *   (c) Früh-Return:          `if (ids.every(park.istGeparkt)) return null` VOR dem Block
 *
 * Jede darf über eine Zwischenvariable laufen (`const verlaufVerstecken = regVerstecken('verlauf')`);
 * der Wächter löst sie bis zum Fixpunkt auf.
 *
 * ── Was „erzeugt Park-Elemente" heißt ─────────────────────────────────────────────────
 *
 * Direkt (`<Parkbar>`, `parkId`, `<KpiStrip>`) ODER **delegiert**: der Rumpf reicht einen
 * `melde`-Rückruf an ein Composite (dann meldet dieses seine IDs hoch), oder er rendert eine
 * projekteigene Komponente, die ihrerseits Park-Elemente erzeugt. Der Wächter folgt dafür den
 * relativen Imports bis Tiefe {@link MAX_TIEFE}. ⛔ **Ohne diese Auflösung sähe er weniger als
 * die Hälfte:** von 107 Block-Definitionen erzeugen nur 43 ihre Park-Elemente im eigenen Rumpf,
 * die übrigen delegieren (`render: () => analyse.verlauf(…)`).
 *
 * Grenze (bewusst benannt): Er sieht keine Render-Geometrie. Bleibt ein Block leer, weil eine
 * Kind-Komponente unter bestimmten Daten nichts zeichnet, obwohl ihre IDs registriert sind,
 * fängt ihn weder dieser Wächter noch `check:park-idliste`. Dafür gibt es die Vitest-Render-
 * Proben (`src/test/park-huelle-leer.test.tsx`, `waermepumpeBauartVergleich.test.tsx`).
 */
import { readdirSync, readFileSync, statSync, existsSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SRC = join(ROOT, 'src')
const ALLOWLIST_PFAD = join(ROOT, 'scripts', 'park-gate-allowlist.json')
const ALLOWLIST = new Set(
  existsSync(ALLOWLIST_PFAD) ? JSON.parse(readFileSync(ALLOWLIST_PFAD, 'utf8')) : [],
)

/** Wie weit der Wächter einer Delegation über Dateigrenzen folgt. Drei Ebenen decken den
 *  Baum ab (Sicht → Sektions-Bauer → Teile-Datei); tiefer wird es Rauschen. */
const MAX_TIEFE = 3

/** Park-Erzeugung im Quelltext: eine Umhüllung, eine Kachel-Park-ID, ein self-parkender
 *  KpiStrip — oder ein hochgereichter `melde`-Rückruf (Composite meldet seine IDs). */
const PARK_DIREKT = /<Parkbar\b|\bparkId\s*[:=]|<KpiStrip\b|\bmelde\b/
/** Die Bezeichner, an denen ein Park-Gate im Baum erkennbar ist. */
const GATE = /\bistGeparkt\b|\balleGeparkt\b|\bsichtbar\b|\bregVerstecken\b|\bparkbareAnzahl\b|Verstecken\b/

function dateien(dir) {
  const out = []
  for (const n of readdirSync(dir)) {
    const p = join(dir, n)
    const s = statSync(p)
    if (s.isDirectory()) out.push(...dateien(p))
    else if (/\.tsx$/.test(n) && !n.includes('.test.')) out.push(p)
  }
  return out
}

const quellen = new Map()
function quelle(pfad) {
  if (!quellen.has(pfad)) {
    const text = readFileSync(pfad, 'utf8')
    quellen.set(pfad, {
      text,
      sf: ts.createSourceFile(pfad, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX),
    })
  }
  return quellen.get(pfad)
}

/** Relative Imports einer Datei → absoluter Pfad, sofern im Baum auflösbar. */
function importZiele(pfad) {
  const { sf } = quelle(pfad)
  const ziele = new Map()
  const geh = (n) => {
    if (ts.isImportDeclaration(n) && ts.isStringLiteral(n.moduleSpecifier)) {
      const spec = n.moduleSpecifier.text
      if (spec.startsWith('.')) {
        const basis = resolve(dirname(pfad), spec)
        const kandidat = ['.tsx', '.ts', '/index.tsx', '/index.ts']
          .map((e) => basis + e)
          .find((p) => existsSync(p))
        if (kandidat) {
          for (const name of importNamen(n)) ziele.set(name, kandidat)
        }
      }
    }
    ts.forEachChild(n, geh)
  }
  geh(sf)
  return ziele
}

function importNamen(decl) {
  const namen = []
  const b = decl.importClause
  if (!b) return namen
  if (b.name) namen.push(b.name.text)
  if (b.namedBindings) {
    if (ts.isNamespaceImport(b.namedBindings)) namen.push(b.namedBindings.name.text)
    else for (const el of b.namedBindings.elements) namen.push(el.name.text)
  }
  return namen
}

/** Erzeugt der Bezeichner `name` aus `pfad` (transitiv) Park-Elemente? */
const symbolCache = new Map()
function symbolErzeugtPark(pfad, name, tiefe, gesehen) {
  const schluessel = `${pfad}#${name}`
  if (gesehen.has(schluessel)) return false
  if (symbolCache.has(schluessel)) return symbolCache.get(schluessel)
  gesehen.add(schluessel)

  const { sf } = quelle(pfad)
  let treffer = false
  const geh = (n) => {
    if (treffer) return
    const istDeklaration =
      (ts.isFunctionDeclaration(n) && n.name?.text === name) ||
      (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.name.text === name)
    if (istDeklaration) {
      if (rumpfErzeugtPark(n.getText(), pfad, tiefe, gesehen)) treffer = true
      return
    }
    ts.forEachChild(n, geh)
  }
  geh(sf)
  symbolCache.set(schluessel, treffer)
  return treffer
}

/**
 * Erzeugt dieser Quelltext-Ausschnitt Park-Elemente — direkt oder über eine Komponente,
 * die aus dem Baum importiert ist?
 */
function rumpfErzeugtPark(rumpf, pfad, tiefe = MAX_TIEFE, gesehen = new Set()) {
  if (PARK_DIREKT.test(rumpf)) return true
  if (tiefe <= 0) return false
  const ziele = importZiele(pfad)
  // JSX-Komponenten und aufgerufene Funktionen aus demselben Baum
  const namen = new Set()
  for (const m of rumpf.matchAll(/<([A-Z][\w]*)\b/g)) namen.add(m[1])
  for (const m of rumpf.matchAll(/\b([a-zA-Z_$][\w$]*)\s*\(/g)) namen.add(m[1])
  for (const name of namen) {
    // Im selben Modul deklariert?
    if (symbolErzeugtPark(pfad, name, tiefe - 1, gesehen)) return true
    const ziel = ziele.get(name)
    if (ziel && symbolErzeugtPark(ziel, name, tiefe - 1, gesehen)) return true
  }
  return false
}

/** Die Gate-Variablen einer Datei (Fixpunkt: eine Variable, die auf einer Gate-Variablen aufbaut,
 *  ist selbst eine). */
function gateVariablen(sf) {
  const set = new Set()
  for (let runde = 0; runde < 4; runde++) {
    const vorher = set.size
    const geh = (n) => {
      if (ts.isVariableDeclaration(n) && n.initializer && ts.isIdentifier(n.name)) {
        const t = n.initializer.getText()
        if (GATE.test(t) || [...set].some((v) => new RegExp(`\\b${v}\\b`).test(t))) set.add(n.name.text)
      }
      ts.forEachChild(n, geh)
    }
    geh(sf)
    if (set.size === vorher) break
  }
  return set
}

const istGateAusdruck = (txt, vars) =>
  GATE.test(txt) || [...vars].some((v) => new RegExp(`\\b${v}\\b`).test(txt))

/** Trägt die umgebende Funktion VOR `knoten` einen Park-Früh-Return? (Gate-Form c) */
function fruehReturnDavor(knoten, vars) {
  let p = knoten.parent
  while (p) {
    if (
      ts.isFunctionDeclaration(p) || ts.isArrowFunction(p) ||
      ts.isFunctionExpression(p) || ts.isMethodDeclaration(p)
    ) {
      const rumpf = p.getText()
      const vor = rumpf.slice(0, Math.max(0, knoten.getStart() - p.getStart()))
      const treffer = [...vor.matchAll(/\bif\s*\(([\s\S]{0,200}?)\)\s*(?:\{\s*)?return\b/g)]
      if (treffer.some((m) => istGateAusdruck(m[1], vars))) return true
    }
    p = p.parent
  }
  return false
}

/** Ist dieser Knoten an ein Park-Gate gebunden? (Gate-Formen a, b, c — auch über Variablen) */
function istGegated(knoten, sf, vars) {
  let p = knoten.parent
  let tiefe = 0
  while (p && tiefe++ < 16) {
    if (ts.isConditionalExpression(p) && istGateAusdruck(p.condition.getText(), vars)) return true
    if (ts.isBinaryExpression(p) && istGateAusdruck(p.left.getText(), vars)) return true
    if (ts.isIfStatement(p) && istGateAusdruck(p.expression.getText(), vars)) return true
    // Der Block liegt in einer Variablen — wird DIESE gegated eingehängt?
    if (ts.isVariableDeclaration(p) && ts.isIdentifier(p.name)) {
      if (variableGegatedVerwendet(sf, p.name.text, vars)) return true
      break
    }
    p = p.parent
  }
  return fruehReturnDavor(knoten, vars)
}

function variableGegatedVerwendet(sf, name, vars) {
  const re = new RegExp(`\\b${name}\\b`)
  let treffer = false
  const geh = (n) => {
    if (treffer) return
    if (ts.isConditionalExpression(n) && istGateAusdruck(n.condition.getText(), vars) && re.test(n.getText())) treffer = true
    else if (ts.isBinaryExpression(n) && istGateAusdruck(n.left.getText(), vars) && re.test(n.right.getText())) treffer = true
    else if (ts.isIfStatement(n) && istGateAusdruck(n.expression.getText(), vars) && re.test(n.getText())) treffer = true
    if (!treffer) ts.forEachChild(n, geh)
  }
  geh(sf)
  return treffer
}

const zeileVon = (text, pos) => text.slice(0, pos).split('\n').length
const kurz = (p) => p.replace(ROOT + '/', '')

// ── Lauf ────────────────────────────────────────────────────────────────────────────
const verstoesse = []
let bloeckeGesamt = 0
let bloeckeMitPark = 0
let huellenGesamt = 0
let huellenMitPark = 0

for (const pfad of dateien(SRC)) {
  const { text, sf } = quelle(pfad)
  if (!/render:|<FokusKachel/.test(text)) continue
  const vars = gateVariablen(sf)

  const geh = (node) => {
    // R1 — Block-Objektliterale
    if (ts.isObjectLiteralExpression(node)) {
      const props = node.properties.filter(ts.isPropertyAssignment)
      const idProp = props.find((p) => p.name.getText() === 'id')
      const renderProp = props.find((p) => p.name.getText() === 'render')
      if (idProp && renderProp) {
        bloeckeGesamt++
        const id = idProp.initializer.getText().replace(/['"`]/g, '')
        const marke = `${kurz(pfad)}::${id}`
        if (rumpfErzeugtPark(renderProp.getText(), pfad)) {
          bloeckeMitPark++
          if (!istGegated(node, sf, vars) && !ALLOWLIST.has(marke)) {
            verstoesse.push({
              regel: 'R1',
              datei: kurz(pfad),
              zeile: zeileVon(text, node.getStart()),
              was: `Block \`${id}\` rendert Park-Elemente, hängt aber ungegated im Bau`,
            })
          }
        }
      }
    }
    // R2 — FokusKachel-Hüllen
    if (ts.isJsxElement(node) && node.openingElement.tagName.getText() === 'FokusKachel') {
      huellenGesamt++
      const inhalt = node.getText()
      if (rumpfErzeugtPark(inhalt, pfad)) {
        huellenMitPark++
        const inParkbar = (() => {
          let p = node.parent
          while (p) {
            if (ts.isJsxElement(p) && p.openingElement.tagName.getText() === 'Parkbar') return true
            p = p.parent
          }
          return false
        })()
        const marke = `${kurz(pfad)}::<FokusKachel>@${zeileVon(text, node.getStart())}`
        if (!inParkbar && !fruehReturnDavor(node, vars) && !ALLOWLIST.has(marke)) {
          verstoesse.push({
            regel: 'R2',
            datei: kurz(pfad),
            zeile: zeileVon(text, node.getStart()),
            was: '<FokusKachel> mit parkbaren Kindern versteckt sich bei Voll-Park nicht',
          })
        }
      }
    }
    ts.forEachChild(node, geh)
  }
  geh(sf)
}

if (verstoesse.length > 0) {
  console.error('\ncheck:park-gate — Auto-Hide-Gate fehlt:\n')
  for (const v of verstoesse) console.error(`  ✗ [${v.regel}] ${v.datei}:${v.zeile} — ${v.was}`)
  console.error(
    '\nDoktrin: parkt der Anwender ALLE Elemente eines Blocks, muss der Block verschwinden.\n' +
    'Drei zulässige Formen (alle im Baum belegt):\n' +
    "  (a) `...(sichtbar(ids) ? [block] : [])` bzw. `!alleGeparkt(ids) ? {…} : null`\n" +
    "  (b) `if (!alleGeparkt(ids)) bloecke.push({…})`\n" +
    "  (c) `if (ids.every(park.istGeparkt)) return null` VOR dem Block\n" +
    'Bei einer <FokusKachel>: entweder in eine <Parkbar> hüllen oder (c).\n' +
    'Ist die Stelle eine begründete Ausnahme → scripts/park-gate-allowlist.json (mit Kommentar im Code).\n',
  )
  process.exit(1)
}

console.log(
  `\ncheck:park-gate — ${bloeckeGesamt} Block-Definitionen (davon ${bloeckeMitPark} mit Park-Elementen) ` +
  `und ${huellenGesamt} <FokusKachel>-Hüllen (davon ${huellenMitPark} mit parkbaren Kindern) geprüft.`,
)
console.log('✅ Jeder Block und jede Hülle mit parkbaren Elementen verschwindet bei Voll-Park.')
