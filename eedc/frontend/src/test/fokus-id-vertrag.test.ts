/**
 * Fokus-IDs sind öffentlicher Vertrag (FD-1) — Snapshot-Wächter.
 *
 * Seit dem Fokus-Deep-Link steht jede Block-ID und jede Kachel-`fokusId` in
 * fremden Home-Assistant-Dashboards: `#/<sicht>?fokus=<id>` ist die Adresse
 * einer Webseiten-Karte. Wer eine ID umbenennt, bricht diese Karten — und zwar
 * **still**, denn die Sicht selbst funktioniert weiter (FD-5 zeigt dann das
 * Hinweis-Overlay). Ohne diesen Wächter fiele das erst beim Anwender auf.
 *
 * ⚠ Er ist **kein** `check:*`-Skript: Vitest reicht, läuft mit `npm test` und
 * `check-einhaengung` bleibt unberührt.
 *
 * ── Was geerntet wird ───────────────────────────────────────────────────────
 *  • **Block-IDs** — Objektliterale mit `id: '…'` UND `render`, also die Form
 *    des `Block`-Modells (`components/blocks/types.ts`). Über die AST-Form statt
 *    über einen Regex auf `id: '…'`: sonst geriete jedes beliebige Objekt mit
 *    einem `id`-Feld in den Vertrag (Gegenprüfung Ü3).
 *    ⚠ **Ohne Zusatzfilter auf die Datei und ohne `title`-Pflicht** — beides am
 *    22.09. gemessen: ein Filter „nur Dateien, die `BlockShell` nennen" verlöre
 *    die acht Block-IDs aus `KomponentenSektionen.tsx`/`MonatRahmen.tsx`
 *    (Bau-Helfer ohne BlockShell-Erwähnung), eine `title`-Pflicht die fünf aus
 *    `CommunityKomponentenV4.tsx` (Titel kommt dort per Spread `...ident(…)`).
 *  • **Kachel-IDs** — `fokusId="…"` / `fokusId: '…'` (`FokusKachel`,
 *    `EinbettenKnopf`).
 *  ⛔ **Nicht** geerntet werden Park-Element-IDs (`el:` · `kpi:` · `chart:` ·
 *    `info:` · `tabelle:` · `badge:`): sie sind eine andere Ebene (der Park
 *    räumt weg, der Deep-Link zeigt her) und kein Deep-Link-Ziel — Gernots
 *    Entscheid vom 22.09. lautet „nur Block-Ebene".
 *
 * Duplikate bleiben stehen (die Aussicht baut `verlauf` je Horizont einmal);
 * geordnet wird je Datei, damit eine Verschiebung im Quelltext nichts auslöst.
 */
import { describe, it, expect } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import ts from 'typescript'

const SRC = join(process.cwd(), 'src')
const SNAPSHOT = join(SRC, 'test', 'fokus-ids.snapshot.json')

/** Park-Element-Präfixe — andere Ebene, kein Deep-Link-Ziel. */
const PARK_PRAEFIXE = ['el:', 'kpi:', 'chart:', 'info:', 'tabelle:', 'badge:']
const istParkElement = (id: string) => PARK_PRAEFIXE.some((p) => id.startsWith(p))

function quelldateien(dir: string): string[] {
  const out: string[] = []
  for (const n of readdirSync(dir)) {
    const p = join(dir, n)
    if (statSync(p).isDirectory()) out.push(...quelldateien(p))
    else if (/\.tsx?$/.test(n) && !n.includes('.test.')) out.push(p)
  }
  return out
}

/** String-Wert einer Objekt-Eigenschaft bzw. eines JSX-Attributs. */
function stringWert(node: ts.Node | undefined): string | null {
  if (node == null) return null
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text
  if (ts.isJsxExpression(node) && node.expression) return stringWert(node.expression)
  return null
}

export function ernteFokusIds(): Record<string, string[]> {
  const treffer: Record<string, string[]> = {}
  for (const pfad of quelldateien(SRC)) {
    const text = readFileSync(pfad, 'utf8')
    const kurz = pfad.replace(process.cwd() + '/', '')
    const sf = ts.createSourceFile(pfad, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
    const ids: string[] = []

    const geh = (n: ts.Node) => {
      // Block-Literal: { id: '…', render: … } — `title` ist nicht Pflicht (s. Kopf).
      if (ts.isObjectLiteralExpression(n)) {
        const props = n.properties.filter(ts.isPropertyAssignment)
        const idProp = props.find((p) => p.name.getText() === 'id')
        const hatRender = n.properties.some((p) => p.name?.getText() === 'render')
        const id = idProp ? stringWert(idProp.initializer) : null
        if (id && hatRender && !istParkElement(id)) ids.push(id)
      }
      // Kachel-ID: fokusId="…" bzw. fokusId: '…'
      if (ts.isJsxAttribute(n) && n.name.getText() === 'fokusId') {
        const id = stringWert(n.initializer)
        if (id && !istParkElement(id)) ids.push(id)
      }
      if (ts.isPropertyAssignment(n) && n.name.getText() === 'fokusId') {
        const id = stringWert(n.initializer)
        if (id && !istParkElement(id)) ids.push(id)
      }
      ts.forEachChild(n, geh)
    }
    geh(sf)
    if (ids.length) treffer[kurz] = ids.sort()
  }
  return treffer
}

describe('Fokus-IDs sind öffentlicher Vertrag (FD-1)', () => {
  it('die geernteten IDs entsprechen dem Snapshot', () => {
    const ist = ernteFokusIds()
    const soll = JSON.parse(readFileSync(SNAPSHOT, 'utf8')) as Record<string, string[]>
    expect(
      ist,
      'Fokus-IDs sind öffentlicher Vertrag (HA-Dashboards); Snapshot bewusst aktualisieren '
      + 'und CHANGELOG-Zeile „Breaking: Deep-Link" schreiben',
    ).toEqual(soll)
  })

  it('erntet keine Park-Element-IDs (andere Ebene, Entscheid „nur Block-Ebene")', () => {
    for (const ids of Object.values(ernteFokusIds())) {
      for (const id of ids) expect(istParkElement(id)).toBe(false)
    }
  })
})
