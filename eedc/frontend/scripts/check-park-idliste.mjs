#!/usr/bin/env node
/**
 * check-park-idliste.mjs — Wächter der Element-Park-Doktrin, Hälfte 4: die ID-LISTE.
 *
 * Ein Auto-Hide-Gate fragt „sind ALLE Element-IDs dieses Blocks geparkt?" und braucht dafür
 * eine Liste. Driftet sie vom real Gerenderten ab, bricht das Gate — und zwar still:
 *
 *   • Eine ID in der Liste, die NIE gerendert wird ⇒ `alleGeparkt` wird **nie wahr** ⇒
 *     der leere Block bleibt stehen. **Das ist der real eingetretene Fall** (Gernot,
 *     2026-07-09): `UEB_PARK_IDS` verlangte fest `ueb-schwaechen`, aber
 *     `StaerkenSchwaechen` rendert es nur bei ≥1 Schwäche. Bei „3 Stärken · 0 Potenzial"
 *     blieb der Block leer im Bild.
 *
 * Deshalb prüft dieser Wächter zwei Regeln:
 *
 *   L1 — **jede ID einer Gate-Liste hat eine Erzeugungsstelle** (SOLL ⊆ IST). Fängt die
 *        gelöschte, umbenannte oder vertippte ID, die in der Liste stehen blieb.
 *   L2 — **eine ID in einer FEST deklarierten Liste wird UNBEDINGT gerendert.** Hängt ihr
 *        `<Parkbar>` in einem datenabhängigen Zweig, wird `alleGeparkt` für Anwender ohne
 *        diese Daten nie wahr — der leere Block bleibt stehen. ⭐ **Das ist die Regel, die
 *        den Referenzfall trifft:** `ueb-schwaechen` EXISTIERT als Literal, es wird nur
 *        bedingt gerendert. L1 allein hätte ihn nicht gefangen — gemessen mit einem
 *        Sprengsatz, der still blieb.
 *
 * ⛔ Ausgenommen sind Bedingungen, die SELBST ein Park-Gate sind (`{!tabelleGeparkt && …}`):
 * dass ein geparktes Element nicht rendert, ist die Park-Mechanik, nicht ihre Verletzung.
 *
 * Die Gegenrichtung (ein gerendertes Element fehlt in der Liste) bleibt statisch NICHT
 * entscheidbar — dafür gibt es die Render-Proben (`waermepumpeBauartVergleich.test.tsx`).
 *
 * ── Erzeugungsstellen ────────────────────────────────────────────────────────────────
 *   • `<Parkbar id="…">`              — die Umhüllung selbst
 *   • `parkId: '…'` / `parkId="…"`    — self-parkende KpiStrip-/FormBlock-Kacheln
 *   • dynamisch: ``id={`praefix-${…}`}`` bzw. ``parkId: `praefix-${…}` `` — eine Listen-ID
 *     gilt als gedeckt, wenn sie auf ein solches Präfix passt.
 *   • **per Konstruktion**: `parkId: PARK_IDS_KPI[0]` — die Liste IST die Quelle der
 *     gerenderten ID. Das ist die driftfreie Bauform (`SpeicherPotentialIST.tsx`, dort im
 *     Kommentar: *„an EINER Stelle, weil sie zweimal gebraucht werden … zwei Listen wären
 *     die nächste Drift-Quelle"*). Sie kann per Definition nicht driften und wird getrennt
 *     ausgewiesen. ⛔ Der erste Entwurf dieses Wächters meldete sie als Verstoß — er hätte
 *     also ausgerechnet die vorbildliche Form bestraft und zur schlechteren gedrängt.
 *
 * ⚠ **Die Grenze des Präfix-Zweigs, ausdrücklich benannt:** Ein kurzes Präfix wie `kpi:`
 * deckt jede `kpi:*`-ID ab — der Wächter kann `slug(k.title)` nicht ausrechnen. Er weist
 * deshalb getrennt aus, wie viele IDs **nur** per Präfix gedeckt sind; steigt diese Zahl
 * stark, deckt der Wächter weniger, als seine Meldung nahelegt (N-318-Lehre: eine Zahl,
 * die jemand lesen kann, statt eines Hakens).
 *
 * Ersetzt zusammen mit `check:park-gate` den `check:park-leertest` (Playwright, 188 s),
 * der am 2026-09-06 grün über ein Element meldete, das er nie gesehen hatte.
 */
import { readdirSync, readFileSync, statSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SRC = join(ROOT, 'src')
const ALLOWLIST_PFAD = join(ROOT, 'scripts', 'park-idliste-allowlist.json')
const ALLOWLIST = new Set(
  existsSync(ALLOWLIST_PFAD) ? JSON.parse(readFileSync(ALLOWLIST_PFAD, 'utf8')) : [],
)

/** Aufrufe, deren Argument eine Park-ID-Liste ist. */
const GATE_AUFRUF = /^(alleGeparkt|sichtbar|regVerstecken|parkIdsVon|einSichtbar)$/

function dateien(dir) {
  const out = []
  for (const n of readdirSync(dir)) {
    const p = join(dir, n)
    const s = statSync(p)
    if (s.isDirectory()) out.push(...dateien(p))
    else if (/\.tsx?$/.test(n) && !n.includes('.test.')) out.push(p)
  }
  return out
}

const alleDateien = dateien(SRC)
const parse = (pfad) => {
  const text = readFileSync(pfad, 'utf8')
  return { text, sf: ts.createSourceFile(pfad, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX) }
}

// ── 1. Erzeugungsstellen baumweit einsammeln ────────────────────────────────────────
const literale = new Set()
const praefixe = new Set()
/** Listen-Namen, die SELBST die Quelle einer gerenderten `parkId` sind. */
const alsQuelleVerwendet = new Set()
for (const pfad of alleDateien) {
  const text = readFileSync(pfad, 'utf8')
  for (const m of text.matchAll(/<Parkbar\b[^>]*?\bid="([^"]+)"/g)) literale.add(m[1])
  for (const m of text.matchAll(/\bparkId\s*[:=]\s*['"]([^'"]+)['"]/g)) literale.add(m[1])
  // dynamisch: id={`praefix-${…}`} / parkId: `praefix-${…}`
  for (const m of text.matchAll(/\b(?:id|parkId)\s*[:=]\s*\{?\s*`([^`$]*)\$\{/g)) {
    if (m[1]) praefixe.add(m[1])
  }
  // per Konstruktion: `parkId: LISTE[0]` / `parkId={LISTE[i]}`
  for (const m of text.matchAll(/\bparkId\s*[:=]\s*\{?\s*([A-Za-z_$][\w$]*)\s*\[/g)) {
    alsQuelleVerwendet.add(m[1])
  }
}

const gedeckt = (id) => (literale.has(id) ? 'literal' : ([...praefixe].some((p) => id.startsWith(p)) ? 'praefix' : null))

// ── 1b. Welche Parkbar-IDs werden nur BEDINGT gerendert? (L2) ───────────────────────
/** Eine Bedingung, die selbst ein Park-Gate ist — sie zählt nicht als datenabhängig. */
const IST_PARK_BEDINGUNG = /istGeparkt|[Gg]eparkt\b/
const bedingtGerendert = new Map()
for (const pfad of alleDateien) {
  const { sf } = parse(pfad)
  const kurz = pfad.replace(ROOT + '/', '')
  const geh = (n) => {
    const istParkbar =
      (ts.isJsxElement(n) && n.openingElement.tagName.getText() === 'Parkbar') ||
      (ts.isJsxSelfClosingElement(n) && n.tagName.getText() === 'Parkbar')
    if (istParkbar) {
      const attrs = (ts.isJsxElement(n) ? n.openingElement : n).attributes
      const idAttr = attrs.properties.find(
        (p) => ts.isJsxAttribute(p) && p.name.getText() === 'id',
      )
      if (idAttr?.initializer && ts.isStringLiteral(idAttr.initializer)) {
        const id = idAttr.initializer.text
        let p = n.parent
        let tiefe = 0
        let bedingung = null
        while (p && tiefe++ < 10) {
          if (ts.isBinaryExpression(p) && p.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken) {
            bedingung = p.left.getText(); break
          }
          if (ts.isConditionalExpression(p)) { bedingung = p.condition.getText(); break }
          if (ts.isArrowFunction(p) || ts.isFunctionDeclaration(p)) break
          p = p.parent
        }
        // Nur DATENabhängige Bedingungen zählen; ein Park-Gate ist die Mechanik selbst.
        // Bei `hatVerlauf && !verlaufGeparkt` bleibt die Datenhälfte übrig ⇒ zählt.
        if (bedingung) {
          const ohnePark = bedingung
            .split(/&&/)
            .filter((teil) => !IST_PARK_BEDINGUNG.test(teil))
            .join('&&')
            .trim()
          if (ohnePark) bedingtGerendert.set(id, `${kurz} — nur bei \`${ohnePark.slice(0, 70)}\``)
        }
      }
    }
    ts.forEachChild(n, geh)
  }
  geh(sf)
}

// ── 2. Gate-Listen einsammeln ───────────────────────────────────────────────────────
/** String-Literale eines Ausdrucks (Array- oder Objekt-Literal aus Arrays). */
function stringsAus(node) {
  const out = []
  const geh = (n) => {
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n)) out.push(n.text)
    ts.forEachChild(n, geh)
  }
  geh(node)
  return out
}

const listen = []
for (const pfad of alleDateien) {
  const { sf } = parse(pfad)
  const kurz = pfad.replace(ROOT + '/', '')

  // Deklarationen: Namenskonvention `*PARK_IDS*` ODER ein Bezeichner, der an einen
  // Gate-Aufruf geht. Beide Wege, damit auch die INLINE-Listen erfasst sind
  // (`const bilanzIds = [...]` in AuswertungenCo2V4 — sie heißen nicht `*_PARK_IDS`,
  // sind aber dieselbe Sache; wer nur die Konvention prüft, sieht 7 statt 17 Dateien).
  const gateArgumente = new Set()
  const sammleAufrufe = (n) => {
    if (ts.isCallExpression(n)) {
      const name = ts.isIdentifier(n.expression) ? n.expression.text
        : (ts.isPropertyAccessExpression(n.expression) ? n.expression.name.text : '')
      if (GATE_AUFRUF.test(name)) {
        for (const arg of n.arguments) {
          if (ts.isIdentifier(arg)) gateArgumente.add(arg.text)
          else if (ts.isPropertyAccessExpression(arg)) gateArgumente.add(arg.expression.getText())
          else if (ts.isArrayLiteralExpression(arg)) {
            listen.push({ datei: kurz, name: '(inline)', ids: stringsAus(arg) })
          }
        }
      }
      // `ids.every((id) => park.istGeparkt(id))` — die Liste steht links vom `.every`
      if (ts.isPropertyAccessExpression(n.expression) && n.expression.name.text === 'every'
          && /istGeparkt/.test(n.getText())) {
        const ziel = n.expression.expression
        if (ts.isIdentifier(ziel)) gateArgumente.add(ziel.text)
        else if (ts.isPropertyAccessExpression(ziel)) gateArgumente.add(ziel.expression.getText())
        else if (ts.isArrayLiteralExpression(ziel)) {
          listen.push({ datei: kurz, name: '(inline)', ids: stringsAus(ziel) })
        }
      }
    }
    ts.forEachChild(n, sammleAufrufe)
  }
  sammleAufrufe(sf)

  const sammleDeklarationen = (n) => {
    if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.initializer) {
      const name = n.name.text
      const relevant = /PARK_IDS/i.test(name) || gateArgumente.has(name)
      if (relevant && (ts.isArrayLiteralExpression(n.initializer)
        || ts.isObjectLiteralExpression(n.initializer)
        || ts.isAsExpression(n.initializer))) {
        const ids = stringsAus(n.initializer)
        // „Fest" = eine Konstante auf Modulebene mit `as const`: ihre Elementmenge
        // steht vor jeder Datenlage fest. Eine im Funktionsrumpf aus den Daten
        // gebaute Liste (`...(posten.length > 0 ? ['tabelle:…'] : [])`) ist nicht fest.
        const fest = ts.isAsExpression(n.initializer)
          && n.parent?.parent?.parent?.kind === ts.SyntaxKind.SourceFile
        if (ids.length) listen.push({ datei: kurz, name, ids, fest })
      }
    }
    ts.forEachChild(n, sammleDeklarationen)
  }
  sammleDeklarationen(sf)
}

// ── 3. Prüfen ───────────────────────────────────────────────────────────────────────
const verstoesse = []
let idsGesamt = 0
let nurPraefix = 0
let perKonstruktion = 0
for (const l of listen) {
  // Ist die Liste selbst die Quelle der gerenderten IDs, kann sie nicht driften.
  if (alsQuelleVerwendet.has(l.name)) {
    idsGesamt += l.ids.length
    perKonstruktion += l.ids.length
    continue
  }
  for (const id of l.ids) {
    idsGesamt++
    const art = gedeckt(id)
    if (art === 'praefix') nurPraefix++
    if (!art && !ALLOWLIST.has(id)) {
      verstoesse.push({ regel: 'L1', datei: l.datei, liste: l.name, id,
        was: 'wird nirgends gerendert' })
    } else if (l.fest && bedingtGerendert.has(id) && !ALLOWLIST.has(id)) {
      verstoesse.push({ regel: 'L2', datei: l.datei, liste: l.name, id,
        was: `steht FEST in der Liste, wird aber bedingt gerendert (${bedingtGerendert.get(id)})` })
    }
  }
}

if (verstoesse.length > 0) {
  console.error('\ncheck:park-idliste — Park-ID ohne Erzeugungsstelle:\n')
  for (const v of verstoesse) console.error(`  ✗ [${v.regel}] ${v.datei} · ${v.liste} → „${v.id}" ${v.was}`)
  console.error(
    '\nFolge: `alleGeparkt` wird für diesen Block NIE wahr — parkt der Anwender alles,\n' +
    'bleibt der leere Block im Bild stehen (der Fall UEB_PARK_IDS/`ueb-schwaechen`).\n' +
    'Entweder die ID aus der Liste nehmen oder — wenn sie datenabhängig ist — die Liste\n' +
    'aus den Daten ABLEITEN (Muster `uebAchievementParkIds`) statt sie fest zu schreiben.\n',
  )
  process.exit(1)
}

console.log(
  `\ncheck:park-idliste — ${listen.length} Gate-Listen mit ${idsGesamt} Park-IDs geprüft ` +
  `(${literale.size} Literale + ${praefixe.size} dynamische Präfixe im Baum; ` +
  `${nurPraefix} ID(s) nur per Präfix gedeckt, ${perKonstruktion} per Konstruktion).`,
)
console.log(
  `   ${bedingtGerendert.size} Park-ID(s) werden datenabhängig gerendert — keine davon steht fest in einer Liste.`,
)
console.log('✅ Jede ID einer Auto-Hide-Liste hat eine Erzeugungsstelle — kein Gate, das nie wahr wird.')
