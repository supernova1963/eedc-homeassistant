#!/usr/bin/env node
/**
 * check-ergebnis-roh.mjs — Cockpit Monat/Jahr und Finanzen rechnen nicht mit Antwortwerten (W2).
 *
 * Paket „Ergebnisgrößen Monat/Jahr in den Layer" (03.10.2026, Vorlage B6/W2, Gegenprüfung G7). Die Client-Hälfte der
 * Regel, die `backend/tests/test_ergebnis_leiter_nur_im_layer.py` (W1) im Backend hält: Netto-Ertrag, Monats-/
 * Jahresergebnis, SOLL-Erfüllung, Jahresquoten und die Jahresfaltung entstehen im Backend-Layer
 * (`core/berechnungen/ergebnis.py`) und kommen samt Herleitung als Felder. Bis dahin standen sie hier:
 * `MonatBilanz.tsx` (Monatsergebnis aus dem Sammelfeld, N-600), `JahrBilanz.tsx` (Jahresergebnis), `lib/sollErfuellung.ts`
 * (Quote), `v4/JahrAggregat.tsx` (die ganze Jahresfaltung, 690 Zeilen — N-584: 198 % Autarkie).
 *
 * **Die Regel, am Syntaxbaum:** in den Dateien des Geltungsbereichs steht keine Rechenoperation (`+ − * /` und ihre
 * Zuweisungsformen), deren Operand ein Antwortfeld `*_euro | *_kwh | *_prozent | *_cent` liest — auch nicht über
 * `?? 0`, Klammern oder Negation. Ausgenommen ist die String-Verkettung (`fmtCalc(x_euro) + ' €'`), denn sie rechnet
 * nicht.
 *
 * **Ausnahmen** sind klassifiziert — Datei + umgebende Funktion/Variable — und tragen einen Grund
 * (`AUSNAHMEN` unten). Eine Ausnahme ohne Fundstelle ist rot: sie wäre ein Persil-Schein für die nächste.
 *
 * **Grenzen (gemessen beim Bau, keine Fußnote):**
 *  (a) Ein Feld, das erst über eine neutral benannte Variable in die Rechnung kommt (`const e = d.x_euro; e * 2`),
 *      läuft vorbei — dieselbe Grenze wie `check:co2-roh` (d). Die Herleitung des Backends macht solche Umwege
 *      unnötig; ein Review sieht sie.
 *  (b) Geltungsbereich ist die Fläche der Ergebnisgrößen (Cockpit Monat/Jahr, Finanzen, SOLL-Kachel). Andere Sichten
 *      (Tag, Komponenten-Hubs, Live) bewacht dieser Prüfer nicht — Cockpit → Tag (`baueTagAlsMonat`) ist dieselbe
 *      Klasse auf der Tagesachse und ein eigenes Paket (Vorlage §9 Nr. 5).
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SRC = join(ROOT, 'src')

/** Geltungsbereich (Vorlage W2). */
const GELTUNG = [
  /^src\/v4\/Monat[^/]*\.tsx?$/,
  /^src\/v4\/Jahr[^/]*\.tsx?$/,
  /^src\/v4\/Cockpit(Monat|Jahr)V4\.tsx$/,
  /^src\/components\/finanzen\/[^/]*\.tsx?$/,
  /^src\/components\/blocks\/GrundlastSollIstKachel\.tsx$/,
  /^src\/lib\/sollErfuellung\.ts$/,
]

const FELD = /_(euro|kwh|prozent|cent)$/
const OPERATOREN = new Set([
  ts.SyntaxKind.PlusToken, ts.SyntaxKind.MinusToken, ts.SyntaxKind.AsteriskToken, ts.SyntaxKind.SlashToken,
  ts.SyntaxKind.PlusEqualsToken, ts.SyntaxKind.MinusEqualsToken, ts.SyntaxKind.AsteriskEqualsToken,
  ts.SyntaxKind.SlashEqualsToken,
])

/**
 * Klassifizierte Ausnahmen: `datei::Funktion/Variable` → Grund. Die Fläche rechnet hier keine Ergebnisgröße, sondern
 * stellt dar (Balkenbreite, Δ-Anzeige) oder verteilt Posten, deren Gleichheit mit der Leiter eine Probe misst.
 */
export const AUSNAHMEN = {
  'src/components/finanzen/TKonto.tsx::baueTKonto':
    'T-Konto-Hauptbuch: Kontenform derselben Posten (Σ HABEN − Σ SOLL, Bilanzausgleich) und die '
    + 'Restaufteilung der EV-Ersparnis (PV-Zeile = EV − Komponenten-Anteil) — die Gleichheit mit `ergebnis_euro` misst P8 (E2)',
  'src/components/finanzen/KomponentenFinanzTabelle.tsx::zeilenAus':
    'Komponenten-Attribution aus den T-Konto-Posten (Erträge · Einsparungen · Aufwand je Zeile) — Gleichheit mit der Leiter misst P8 (E2)',
  'src/components/finanzen/evAufteilung.ts::pvEigenverbrauchRestEuro':
    'EV-Aufteilung auf T-Konto-Zeilen (PV-Rest = EV-Ersparnis − Komponenten-Anteil, #402) — keine eigene Ergebnisgröße',
  'src/components/finanzen/evAufteilung.ts::bkwAufteilung':
    'EV-Aufteilung des Balkonkraftwerks (A2, 03.10.2026): Anteil der Gerätezeile im Eigenverbrauch, geklemmt wie der '
    + 'PV-Rest; der P9-Rest steht daneben — Gleichheit mit `ergebnis_euro` misst W3(f) über zwölf Monate und das Jahr',
  'src/components/finanzen/evAufteilung.ts::evInKomponentenzeilen':
    'EV-Aufteilung auf T-Konto-Zeilen (Σ der in Komponentenzeilen gebuchten EV-Ersparnis, #402)',
  'src/v4/MonatsRail.tsx::MonatsRail': 'Balkenbreite der Rail (Anzeige, keine Kennzahl)',
  'src/v4/JahresRail.tsx::JahresRail': 'Balkenbreite der Rail (Anzeige, keine Kennzahl)',
  'src/v4/CockpitJahrV4.tsx::railEntries':
    'Rail-Σ PV je Jahr aus der Monatsreihe (Mini-Balken + Titel der Jahres-Rail) — eine Zeitleisten-Anzeige, keine Ergebnisgröße',
  'src/v4/CockpitMonatV4.tsx::gleicheMonatStats':
    'N-604: „Ø gleicher Monat" (Mittel über andere Jahre, Autarkie paarweise) — Client-Rechnung, bis die Monatsreihe eine '
    + 'Backend-Vergleichsroute hat (Register N-604, Trigger dort)',
}

function dateien(dir) {
  const out = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) out.push(...dateien(p))
    else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) && !/\.d\.ts$/.test(name)) out.push(p)
  }
  return out
}

const istString = (n) =>
  ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) || ts.isTemplateExpression(n)

/** Liest der Ausdruck (ohne in Aufrufe, Funktionen oder Strings hineinzusehen) ein Antwortfeld? */
function liestFeld(n) {
  if (ts.isPropertyAccessExpression(n)) return FELD.test(n.name.text) || liestFeld(n.expression)
  if (ts.isElementAccessExpression(n)) {
    const a = n.argumentExpression
    return (a && ts.isStringLiteral(a) && FELD.test(a.text)) || liestFeld(n.expression)
  }
  if (ts.isParenthesizedExpression(n) || ts.isNonNullExpression(n) || ts.isAsExpression(n)) return liestFeld(n.expression)
  if (ts.isPrefixUnaryExpression(n)) return liestFeld(n.operand)
  if (ts.isBinaryExpression(n)) return liestFeld(n.left) || liestFeld(n.right)
  if (ts.isConditionalExpression(n)) return liestFeld(n.whenTrue) || liestFeld(n.whenFalse)
  return false
}

/**
 * Der Träger einer Fundstelle — der stabile Schlüssel einer Ausnahme: die innerste `useMemo`/`useCallback`-Variable,
 * sonst die äußerste benannte Funktion bzw. Top-Level-Variable der Datei (Komponente, Bauer, Hilfsfunktion).
 */
function traeger(n) {
  let hook = null
  let aussen = null
  for (let p = n.parent; p; p = p.parent) {
    if (!hook && ts.isVariableDeclaration(p) && ts.isIdentifier(p.name) && p.initializer
      && ts.isCallExpression(p.initializer) && /^use(Memo|Callback)$/.test(p.initializer.expression.getText())) {
      hook = p.name.text
    }
    if ((ts.isFunctionDeclaration(p) || ts.isMethodDeclaration(p)) && p.name) aussen = p.name.getText()
    if (ts.isVariableDeclaration(p) && ts.isIdentifier(p.name) && ts.isVariableStatement(p.parent.parent)
      && ts.isSourceFile(p.parent.parent.parent)) aussen = p.name.text
  }
  return hook ?? aussen ?? '(Modul)'
}

export function pruefe() {
  const funde = []
  const getroffen = new Set()
  let geprueft = 0
  for (const f of dateien(SRC)) {
    const rel = relative(ROOT, f).replaceAll('\\', '/')
    if (!GELTUNG.some((r) => r.test(rel))) continue
    geprueft++
    const sf = ts.createSourceFile(f, readFileSync(f, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
    const geh = (n) => {
      if (ts.isBinaryExpression(n) && OPERATOREN.has(n.operatorToken.kind)) {
        const plus = n.operatorToken.kind === ts.SyntaxKind.PlusToken
        const verkettung = plus && (istString(n.left) || istString(n.right))
        if (!verkettung && (liestFeld(n.left) || liestFeld(n.right))) {
          const schluessel = `${rel}::${traeger(n)}`
          const zeile = sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1
          if (schluessel in AUSNAHMEN) getroffen.add(schluessel)
          else funde.push({ schluessel, zeile, text: n.getText(sf).replace(/\s+/g, ' ').slice(0, 140) })
        }
      }
      ts.forEachChild(n, geh)
    }
    geh(sf)
  }
  const tot = Object.keys(AUSNAHMEN).filter((k) => !getroffen.has(k))
  return { funde, tot, geprueft }
}

const istHaupt = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]
if (istHaupt) {
  const { funde, tot, geprueft } = pruefe()
  console.log(`check:ergebnis-roh — ${geprueft} Dateien geprüft · ${funde.length} Rechnung(en) mit Antwortfeldern · `
    + `${Object.keys(AUSNAHMEN).length} klassifizierte Ausnahme(n), davon ${tot.length} ohne Fundstelle.`)
  for (const f of funde) console.log(`  ✗ ${f.schluessel.split('::')[0]}:${f.zeile} (${f.schluessel.split('::')[1]}) — ${f.text}`)
  for (const t of tot) console.log(`  ✗ Ausnahme ohne Fundstelle (streichen): ${t}`)
  if (funde.length || tot.length) {
    console.log('\nErgebnisgrößen entstehen im Backend-Layer (core/berechnungen/ergebnis.py) und kommen samt Herleitung als'
      + '\nFelder (`ergebnis_euro`, `ergebnis_herleitung`, `soll_erfuellung_prozent`, Jahresroute `/cockpit/jahr`).'
      + '\nFehlt ein Feld: Backend ergänzen. Echte Darstellung (Balkenbreite, Δ-Anzeige): Ausnahme mit Grund.')
    process.exit(1)
  }
  console.log('✅ Cockpit Monat/Jahr und Finanzen rechnen nicht mit Antwortwerten.')
}
