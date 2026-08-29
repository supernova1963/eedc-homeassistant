/**
 * N-350 — jede Stelle, die einen Community-JAZ **vergleicht**, ruft den SoT
 * `lib/jazVergleich.ts`. Niemand entscheidet die Bezugsgruppe noch einmal selbst.
 *
 * ⛔ **Warum ein Verbots-Grep auf `jaz_typ` hier NICHTS misst — das ist der Kern.**
 * Im Vorzustand las `CommunityKomponentenTeile.tsx` schlicht `kpi={wp.jaz}`; das Wort
 * `jaz_typ` kam dort **gar nicht vor**. Ein Wächter, der „kein inline `jaz_typ`"
 * verlangt, wäre über dem Fund grün gewesen. Deshalb prüft dieser hier die
 * **Gegenrichtung**: Wer `community_avg` auf einem `jaz`-Feld liest, muss den SoT
 * gerufen haben.
 *
 * ⚠ **Die Regel wurde vor diesem Wächter schon zweimal gebaut** — `e36758b7`
 * (Issue #85) und `3717c7c0`, beide nur in `UebersichtTab.tsx`. Die Komponenten-Seite
 * entstand später (`de423238`) und erbte sie nicht. Genau diese Folgewelle soll hier
 * nicht wieder unbemerkt entstehen.
 *
 * Präzedenz für die Bauform (Quelltext-Wächter als reiner Vitest-Test, ohne eigenes
 * `.mjs` und ohne `check:*`-Eintrag): `src/test/bkw-kwp-formel-sot.test.ts`.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const SRC = join(process.cwd(), 'src')
const TESTS = join(SRC, 'test')
const SOT = join(SRC, 'lib/jazVergleich.ts')
/** Der Vertrag selbst — hier stehen die Felder, hier wird nichts entschieden. */
const TYPEN = [join(SRC, 'api/community.ts'), join(SRC, 'api/communityDemo.ts')]

function alleQuelldateien(dir: string): string[] {
  if (dir === TESTS) return []
  return readdirSync(dir).flatMap((eintrag) => {
    const pfad = join(dir, eintrag)
    if (statSync(pfad).isDirectory()) return alleQuelldateien(pfad)
    return /\.tsx?$/.test(pfad) && !/\.test\.tsx?$/.test(pfad) ? [pfad] : []
  })
}

/**
 * Liest diese Datei einen JAZ-**Vergleichswert**?
 *
 * ⚠ **Auf `community_avg` verengt, und das ist Absicht.** `wp.jaz.wert` allein ist
 * kein Vergleich (das Achievement „Wärmekönig" prüft die absolute Schwelle 4.0), und
 * `wp.jaz.rang` / `.von` sind es auch nicht: `jaz_typ` trägt serverseitig **weder**
 * Rang noch `von` (`eedc-community/backend/api/benchmark.py:700-704` konstruiert es
 * nur mit `wert` und `community_avg`) — der RangBadge in `CommunityKomponentenV4.tsx`
 * MUSS deshalb auf `jaz` bleiben und ist keine Fundstelle.
 *
 * ⚠ **Nachbarfelder mit Wortgrenze ausgeschlossen:** `durchschnitt_jaz` und
 * `avg_wp_jaz` sind Regionen-Aggregate aus einer anderen Route und haben mit der
 * Bezugsgruppen-Frage nichts zu tun.
 */
function liestJazVergleich(quelle: string): boolean {
  // ⛔ Die Wortgrenze schliesst NUR `\w` aus, NICHT den Punkt — das ist gemessen.
  // Der erste Entwurf schrieb `(?<![\w.])` und blieb beim Sprengsatz stumm: damit
  // faellt `wp.jaz.community_avg` heraus, also genau die Feldzugriffe, die der
  // Pruefer fangen soll. `durchschnitt_jaz` / `avg_wp_jaz` bleiben trotzdem drausen,
  // sie tragen einen Unterstrich vor `jaz` und der IST `\w`.
  return /(?<!\w)jaz(_typ)?\b[\s\S]{0,40}?community_avg/.test(ohneKommentare(quelle))
}

function ohneKommentare(quelle: string): string {
  return quelle.replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '')
}

/**
 * ⛔ **Kommentare MÜSSEN weg, und das ist gemessen, nicht vorsorglich.** Der erste
 * Entwurf prüfte `/jazVergleichAnzeige/` auf der Rohquelle — beim Sprengsatz-Durchgang
 * am 29.08.2026 blieb er grün, obwohl der Aufruf vollständig entfernt war: In der
 * Datei stand noch ein **Kommentar**, der den Helfernamen erwähnt („rendert bei
 * `jazVergleichAnzeige(...).kpi`"). Ein Prüfer, der Prosa für Code hält, misst nichts.
 * Deshalb zusätzlich auf die öffnende Klammer verengt — der Name allein ist ein Wort,
 * kein Aufruf.
 */
function ruftSoT(quelle: string): boolean {
  return /jazVergleichAnzeige\s*\(/.test(ohneKommentare(quelle))
}

describe('N-350 — der Community-JAZ-Vergleich hat einen Ort', () => {
  const kandidaten = alleQuelldateien(SRC).filter((p) => p !== SOT && !TYPEN.includes(p))

  it('keine Quelldatei liest einen JAZ-Vergleichswert ohne den SoT zu rufen', () => {
    const verstoesse = kandidaten
      .filter((pfad) => {
        const quelle = readFileSync(pfad, 'utf8')
        return liestJazVergleich(quelle) && !ruftSoT(quelle)
      })
      .map((p) => relative(SRC, p))

    expect(verstoesse).toEqual([])
  })

  it('die drei Anzeigestellen rufen den SoT tatsächlich — die Naht, nicht nur das Verbot', () => {
    // Ohne diesen Fall bliebe der Wächter grün, wenn jemand den Vergleich ersatzlos
    // entfernt: „keine Verstöße" ist dann trivial wahr.
    const nahtstellen = [
      'pages/community/CommunityUebersichtTeile.tsx',
      'pages/community/CommunityKomponentenTeile.tsx',
    ]
    for (const rel of nahtstellen) {
      const quelle = readFileSync(join(SRC, rel), 'utf8')
      expect(ruftSoT(quelle), `${rel} ruft jazVergleichAnzeige nicht`).toBe(true)
    }

    // In der Übersicht sind es DREI Vergleichsstellen (Abweichungs-Liste, Radar,
    // Komponenten-Karte) — sie waren am 29.08. der Grund, den Schnitt nachzumessen:
    // die Radar-Stelle stand nicht im ursprünglichen Fundtext.
    const uebersicht = ohneKommentare(
      readFileSync(join(SRC, 'pages/community/CommunityUebersichtTeile.tsx'), 'utf8'),
    )
    expect(uebersicht.match(/jazVergleichAnzeige\s*\(/g)?.length ?? 0).toBeGreaterThanOrEqual(3)
  })

  // ⛔ **Die Inline-Label-Kette wird hier BEWUSST NICHT geprüft** (Tor 3 für die Lösung,
  // Gernots Regel vom 29.08.). Ein eigener Fall dafür wäre ein zweiter Turm:
  // `scripts/check-label-maps.mjs` IST der SoT-Wächter über Enum→Label-Maps in
  // `lib/constants.ts` und führt eine Musterliste — dort steht seit N-350 die Zeile
  // `=== 'luft_wasser' ?` → „WP_ART_LABELS nutzen". Gefahren wird er über
  // `npm run check:label-maps` und den Wrapper `src/test/check-label-maps.test.ts`.
})
