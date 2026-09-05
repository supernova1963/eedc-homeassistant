#!/usr/bin/env node
/**
 * check-bauart-roh.mjs — die Client-Hälfte von ADR-002/**P13** (05.09.2026).
 *
 * **Die Regel (SOLL Wärme/Klima §3.2a, R1):** *Angeboten wird jede Größe, die das
 * Gerät liefern kann — und was es liefern kann, sagt der zugeordnete Zähler,
 * nicht seine Bauart.* Es gibt keine bauartabhängige Feldliste; die Bauart
 * (`wp_art`: luft_wasser · luft_luft · brauchwasser …) darf **vorschlagen**
 * (Vorbelegung, Beschriftung, weiche Herabstufung), eine **Kennzahl abgrenzen**
 * (zwei Bauarten ergeben keine gemeinsame Arbeitszahl, E1) und als
 * **Stammdatum** durchgereicht werden — aber nie entscheiden, welche Größe
 * gemessen, gefordert oder gezeigt wird.
 *
 * **Warum ein Wächter.** Zwischen dem 20.08. und dem 05.09.2026 kamen im
 * Backend sechs neue Bauart-Leser dazu, einer alle drei Tage. Der vom 03.09.
 * (`b9807ac4`) entschied die Warmwasser-**Achse** nach Bauart — zwei Tage später
 * wurde genau das auf Beleglage umgebaut (#404), weil der Maintainer fragte
 * „passt das ins Konzept?". Der Wächter stellt diese Frage als roter Test:
 * **jede Datei, die die Bauart liest, steht in der klassifizierten Liste unten —
 * mit ihrer Gruppe.** Eine neue Datei ist rot, bis sie klassifiziert ist.
 *
 * **Was der Wächter sucht:** die Bezeichner `wp_art`, `istLuftLuft` und die
 * Bauart-Literale `luft_luft` · `luft_wasser` · `brauchwasser` in `src/**`
 * (ohne Tests). Kommentare werden zeilentreu neutralisiert — ein Bauart-Wort
 * in einem Kommentar liest nichts. **String-Literale bleiben stehen**: `'luft_luft'`
 * IST hier der Treffer, anders als bei `check:cop-roh`.
 *
 * **Grenzen, benannt:** (a) **Datei-granular**, nicht funktions-granular wie
 * die Backend-Hälfte (`test_wurzelmuster_konformitaet.py::test_p13_*`) — eine
 * zweite Lesestelle in einer bereits gelisteten Datei fällt nicht auf.
 * (b) **Er sieht Leser, nicht Semantik.** Ob ein neuer Leser Gruppe 2 oder ein
 * R1-Verstoß ist, entscheidet, wer ihn einträgt — der Wächter erzwingt nur, dass
 * die Frage gestellt wird. (c) Wer die Bauart über einen Alias liest
 * (`const art = p['wp_' + 'art']`), läuft vorbei.
 *
 * **Beidseitig gesprengt (05.09.2026):** `luft_luft` in einer nicht gelisteten
 * Anzeigedatei ⇒ rot; ein gelisteter Eintrag ohne Treffer ⇒ rot (toter
 * Eintrag); Bauart-Wort nur im Kommentar ⇒ grün.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..')

const BAUART_LESER = /\b(?:wp_art|istLuftLuft|luft_luft|luft_wasser|brauchwasser)\b/g

/**
 * Klassifizierte Leser — `Datei → Gruppe`. Die Gruppen sind die der
 * Backend-Hälfte (P13_AUSNAHMEN), damit beide Listen dieselbe Sprache sprechen.
 *
 *  0 · Definition / Registry   — hier ENTSTEHT die Bauart bzw. ihre Bedingung
 *  1 · Kennzahl-Abgrenzung     — zwei Bauarten, keine gemeinsame Kennzahl (E1/R2)
 *  2 · Vorschlag               — Vorbelegung, Beschriftung, weiche Herabstufung
 *  3 · Stammdatum              — Anzeige/Transport der Bauart als Eigenschaft
 */
const KLASSIFIZIERT = new Map([
  // ── 0 · Definition / Registry ────────────────────────────────────────────
  ['src/lib/investitionParameter.ts', '0 · SoT der Parameter-Namen und `istLuftLuft` (Spiegel von core/investition_parameter.py)'],
  ['src/lib/fieldDefinitions.ts', '0 · Registry: `bedingung: \'!luft_luft\'` u. a. — die EINE Stelle, an der eine Bedingung definiert wird (N-304)'],
  ['src/lib/constants.ts', '0 · WP_ART_LABELS — Anzeigename je Bauart'],
  // ── 1 · Kennzahl-Abgrenzung ─────────────────────────────────────────────
  ['src/lib/jazVergleich.ts', '1 · Bezugsgruppe des JAZ-Vergleichs je Bauart (N-350): dieselbe Kennzahl nur gegen dieselbe Bauart'],
  // ── 2 · Vorschlag ────────────────────────────────────────────────────────
  ['src/components/forms/sections/InvestitionTypFelder/WaermepumpeFelder.tsx', '2 · Formular: Auswahl der Bauart, Hinweise und Vorbelegung — schlägt vor, entscheidet nichts (N-88/F2b)'],
  ['src/components/forms/sections/investitionFormHelpers.ts', '2 · Formular-Defaults: Heizwärme-/Warmwasserbedarf werden für luft_luft NICHT vorbelegt'],
  // ── 3 · Stammdatum ───────────────────────────────────────────────────────
  ['src/api/community.ts', '3 · Community-Vertrag: `wp_art` als Anlagen-Attribut'],
  ['src/api/communityDemo.ts', '3 · Demo-Payload derselben Form'],
  ['src/pages/community/CommunityKomponentenTeile.tsx', '3 · reicht `anlage.wp_art` an jazVergleich (Gruppe 1) durch'],
  ['src/pages/community/CommunityUebersichtTeile.tsx', '3 · reicht `anlage.wp_art` an jazVergleich (Gruppe 1) durch'],
  ['src/v4/CommunityShareBlock.tsx', '3 · zeigt die Bauart als Zeile „Wärmepumpen-Art"'],
])

const stripComments = (src) =>
  src
    .replace(/\/\*[\s\S]*?\*\//g, (t) => t.replace(/[^\n]/g, ' '))
    .replace(/^[ \t]*\/\/.*$/gm, '')
    // JSX-Kommentare `{/* … */}` sind durch die erste Zeile schon neutralisiert.

function quellDateien(dir) {
  const out = []
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) {
      if (name === 'test' || name === '__tests__') continue
      out.push(...quellDateien(p))
    } else if (/\.(ts|tsx)$/.test(name) && !/\.test\.(ts|tsx)$/.test(name) && !name.endsWith('.d.ts')) {
      out.push(p)
    }
  }
  return out
}

const treffer = new Map()   // datei → [zeile, wort]
for (const datei of quellDateien(join(ROOT, 'src'))) {
  const rel = relative(ROOT, datei).split('\\').join('/')
  const zeilen = stripComments(readFileSync(datei, 'utf8')).split('\n')
  zeilen.forEach((z, i) => {
    for (const m of z.matchAll(BAUART_LESER)) {
      if (!treffer.has(rel)) treffer.set(rel, [])
      treffer.get(rel).push(`${i + 1}: ${m[0]}`)
    }
  })
}

const offen = [...treffer.keys()].filter((f) => !KLASSIFIZIERT.has(f)).sort()
const tot = [...KLASSIFIZIERT.keys()].filter((f) => !treffer.has(f)).sort()

if (offen.length === 0 && tot.length === 0) {
  console.log(`✓ check:bauart-roh — ${treffer.size} Datei(en) lesen die Bauart, alle klassifiziert (ADR-002/P13)`)
  process.exit(0)
}
if (offen.length) {
  console.error(`✗ check:bauart-roh — ${offen.length} neue Datei(en) lesen die Bauart ohne Klassifikation (ADR-002/P13, SOLL §3.2a R1):`)
  for (const f of offen) console.error(`  ${f}\n    ${treffer.get(f).slice(0, 4).join('\n    ')}`)
  console.error('\n  R1: was ein Gerät liefern kann, sagt der zugeordnete Zähler, nicht seine Bauart.')
  console.error('  Die Bauart darf vorschlagen (Gruppe 2), eine Kennzahl abgrenzen (1) oder als Stammdatum')
  console.error('  reisen (3) — nie entscheiden, welche Größe gefordert oder gezeigt wird. Eintragen in')
  console.error('  KLASSIFIZIERT mit Gruppe und Grund, oder die Entscheidung an die Beleglage hängen (#404).')
}
if (tot.length) {
  console.error(`✗ check:bauart-roh — ${tot.length} klassifizierte Datei(en) lesen die Bauart nicht mehr (toter Eintrag löschen):`)
  for (const f of tot) console.error(`  ${f}`)
}
process.exit(1)
