#!/usr/bin/env node
/**
 * check-begriffe.mjs — Anzeigetexte sagen „Gesamtverbrauch" oder „Restverbrauch", nie „Hausverbrauch" (N-603).
 *
 * Regel Gernot (03.10.2026, wörtlich): „Wir sollten den Begriff ‚Hausverbrauch' vermeiden und immer die Formel der
 * Berechnung im Tooltip anzeigen." eedc benutzte das Wort mit zwei Bedeutungen — die Live-Kachel meinte
 * Eigenverbrauch + Netzbezug (**Gesamtverbrauch**), Cockpit → Tag und der Energiefluss den Rest nach den separat
 * erfassten Verbrauchern (**Restverbrauch**); „Haushalt" stand für denselben Rest. Dieselbe Klasse wie N-332
 * („Grundlast" bezeichnete zwei Zahlen). Definitionen: GLOSSAR. Backend-Hälfte: `backend/tests/test_begriffe_anwendertexte.py`.
 *
 * **Die Regel, am Syntaxbaum** (Zeichenketten, Template-Teile, JSX-Text — Kommentare und Bezeichner nicht):
 *  1. kein „Hausverbrauch";
 *  2. „Haushalt" als eigenes Wort nur in den klassifizierten Ausnahmen unten (Zusammensetzungen wie
 *     „Haushaltsperspektive", „Haushaltskosten" sind ein anderes Wort und nicht betroffen).
 *
 * Grenze: ein Text, der das Wort aus Teilen zusammensetzt, läuft vorbei — ein Review sieht ihn.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')
const SRC = join(ROOT, 'src')

/** Klassifizierte Ausnahmen für „Haushalt": `datei` → [Textausschnitt, Grund]. */
export const AUSNAHMEN = {
  'src/components/finanzen/TKonto.tsx': [
    ['(Haushalt)', 'Finanz: „Gewinn/Verlust (Haushalt)" ist die Ergebniszeile des T-Kontos (GLOSSAR) — keine Verbrauchsgröße'],
  ],
  'src/components/forms/sections/InvestitionTypFelder/WallboxFelder.tsx': [
    ['Ihr Haushalt hat', 'der Haushalt als Personen/Wirtschaftseinheit (Dienstwagen), keine Verbrauchsgröße'],
  ],
  'src/components/forms/VersorgerSection.tsx': [
    ['Wallbox, Haushalt', 'Beispiel für den Namen eines Zählers, den der Anwender selbst vergibt — keine eedc-Größe'],
  ],
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

function texte(sf) {
  const out = []
  const geh = (n) => {
    if (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) || ts.isTemplateHead(n)
      || ts.isTemplateMiddle(n) || ts.isTemplateTail(n) || ts.isJsxText(n)) {
      out.push({ zeile: sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1, text: n.text ?? n.getText(sf) })
    }
    ts.forEachChild(n, geh)
  }
  geh(sf)
  return out
}

export function pruefe() {
  const funde = []
  const getroffen = new Set()
  for (const f of dateien(SRC)) {
    const rel = relative(ROOT, f).replaceAll('\\', '/')
    const sf = ts.createSourceFile(f, readFileSync(f, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
    for (const { zeile, text } of texte(sf)) {
      if (/Hausverbrauch/.test(text)) funde.push(`${rel}:${zeile} „Hausverbrauch" — ${text.trim().slice(0, 90)}`)
      if (/\bHaushalt\b/.test(text)) {
        const a = (AUSNAHMEN[rel] ?? []).find(([ausschnitt]) => text.includes(ausschnitt))
        if (a) getroffen.add(`${rel}::${a[0]}`)
        else funde.push(`${rel}:${zeile} „Haushalt" — ${text.trim().slice(0, 90)}`)
      }
    }
  }
  const tot = Object.entries(AUSNAHMEN).flatMap(([rel, liste]) => liste.map(([a]) => `${rel}::${a}`))
    .filter((k) => !getroffen.has(k))
  return { funde, tot }
}

const istHaupt = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]
if (istHaupt) {
  const { funde, tot } = pruefe()
  for (const f of funde) console.log(`  ✗ ${f}`)
  for (const t of tot) console.log(`  ✗ Ausnahme ohne Fundstelle (streichen): ${t}`)
  if (funde.length || tot.length) {
    console.log('\nGesamtverbrauch = Eigenverbrauch + Netzbezug · Restverbrauch = Gesamtverbrauch − separat erfasste'
      + '\nVerbraucher (GLOSSAR). „Haushalt" nur mit Grund in AUSNAHMEN.')
    process.exit(1)
  }
  console.log('✅ check:begriffe — kein „Hausverbrauch", „Haushalt" nur in den klassifizierten Ausnahmen.')
}
