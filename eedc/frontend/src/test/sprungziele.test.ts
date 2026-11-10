/**
 * Wächter W-5 «Sprung-Ziele werden gelesen» (Etappe E4 «Daten-Checker: ein Handgriff je Befund», Bauplan §4,
 * Konzept §3.3 S2/S3).
 *
 * Der Export `backend/tests/fixtures/sprungziele.json` (erzeugt aus den Ziel-Bauern, `test_daten_checker_beheben_links_
 * wirken.py`) nennt je Zielseite (`<pfad>#<block>`) die Parameter, die ein «Beheben»-Link dorthin trägt. Hier steht je
 * Zielseite, **wo** sie gelesen werden: entweder eine benannte Parameter-Liste an `useSprungParameter`
 * (`const <LISTE> = [… '<p>' …] as const`) oder `.get('<p>')` in der genannten Datei. Jeder exportierte Parameter muss an
 * einer dieser Stellen stehen; eine Zielseite ohne Eintrag hier ist rot, ebenso ein Parameter ohne Lesestelle. Die Block-Id
 * steht im Einstellungs-Katalog (Spiegel `sprungziele-blockids.test.ts`).
 */
import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

import { EINSTELLUNGEN_KATALOG } from '../config/einstellungenKatalog'

const EXPORT = '../backend/tests/fixtures/sprungziele.json'

/** Eine Lesestelle: die Datei und — wo der Hook liest — der Name der Parameter-Liste. */
interface Lesestelle { datei: string; liste?: string }

/** `block` liest `EinstellungenV4` für jede Einstellungs-Kategorie (`searchParams.get('block')`). */
const BLOCK: Lesestelle = { datei: 'v4/EinstellungenV4.tsx' }

/** Zielseite → ihre Lesestellen (relativ zu `src/`). */
const LESESTELLEN: Record<string, Lesestelle[]> = {
  'einstellungen/daten': [{ datei: 'hooks/useMonatErfassenDeepLink.ts', liste: 'MONAT_SPRUNG' }],
  'einstellungen/daten#monatsdaten': [BLOCK],
  'einstellungen/daten#energieprofil': [BLOCK, { datei: 'hooks/useWerkbankPlanAusUrl.ts' }],
  'einstellungen/datenquellen': [{ datei: 'v4/EinstellungenV4.tsx', liste: 'DATENQUELLEN_SPRUNG' }],
  'einstellungen/integration#import-buendel': [BLOCK, { datei: 'v4/EinstellungenV4.tsx', liste: 'WIZARD_SPRUNG' }],
  'einstellungen/integration#mqtt-broker': [BLOCK],
  'einstellungen/komponenten': [{ datei: 'v4/EinstellungenV4.tsx', liste: 'KOMPONENTEN_SPRUNG' }],
  'einstellungen/stammdaten#anlage': [BLOCK, { datei: 'pages/AnlagenTeile.tsx', liste: 'ANLAGE_SPRUNG' }],
  'einstellungen/stammdaten#solarprognose': [BLOCK, { datei: 'pages/PVGISSettingsTeile.tsx', liste: 'SOLARPROGNOSE_SPRUNG' }],
  'einstellungen/stammdaten#strompreise': [BLOCK, { datei: 'pages/StrompreiseTeile.tsx', liste: 'STROMPREIS_SPRUNG' }],
  'einstellungen/system#protokolle': [BLOCK],
  'komponenten/speicher': [{ datei: 'hooks/useDeepLinkFokus.ts' }],
}

/** Ziel-Bauer ohne Erzeuger-Stelle (heute nur aus Aktionen erreichbar): `ziel_werkbank(karte, plan)`. */
const OHNE_ERZEUGER: Record<string, string[]> = {
  'einstellungen/daten#energieprofil': ['block', 'karte', 'plan'],
}

/** Liest die Lesestelle den Parameter? Mit Liste: `const <liste> = [… '<p>' …] as const` und die Liste geht an
 *  `useSprungParameter(<liste>`; ohne Liste: `.get('<p>')`. */
function liest(text: string, p: string, liste?: string): boolean {
  if (!liste) return new RegExp(`\\.get\\(['"]${p}['"]\\)`).test(text)
  const def = new RegExp(`const ${liste} = \\[([^\\]]*)\\] as const`).exec(text)
  return !!def && new RegExp(`'${p}'`).test(def[1]) && new RegExp(`useSprungParameter\\(${liste}\\b`).test(text)
}

function exportSeiten(): Record<string, string[]> {
  return { ...JSON.parse(readFileSync(EXPORT, 'utf-8')).seiten, ...OHNE_ERZEUGER }
}

describe('W-5: jede Zielseite liest jeden Parameter, den der Ziel-Bauer für sie erzeugt', () => {
  const seiten = exportSeiten()

  it('jede Zielseite des Exports hat ihre Lesestellen', () => {
    expect(Object.keys(seiten).filter((s) => !LESESTELLEN[s])).toEqual([])
  })

  for (const [seite, parameter] of Object.entries(seiten)) {
    it(`${seite}: ${parameter.join(', ')}`, () => {
      const stellen = LESESTELLEN[seite] ?? []
      const ungelesen = parameter.filter((p) => !stellen.some((s) => liest(readFileSync(`src/${s.datei}`, 'utf-8'), p, s.liste)))
      expect(ungelesen).toEqual([])
    })
  }

  it('jede Block-Id einer Zielseite steht im Einstellungs-Katalog', () => {
    const katalog = new Set(EINSTELLUNGEN_KATALOG.map((e) => `einstellungen/${e.kategorie}#${e.id}`))
    const bloecke = Object.keys(seiten).filter((s) => s.includes('#'))
    expect(bloecke.filter((s) => !katalog.has(s))).toEqual([])
  })

  it('der Wächter hat Zähne', () => {
    expect(liest("const x = searchParams.get('feld')", 'feld')).toBe(true)
    const hook = "const L = ['tarif', 'feld'] as const\nuseSprungParameter(L, true)"
    expect(liest(hook, 'feld', 'L')).toBe(true)
    expect(liest(hook.replace(", 'feld'", ''), 'feld', 'L')).toBe(false)          // Parameter fehlt in der Liste
    expect(liest("const L = ['feld'] as const", 'feld', 'L')).toBe(false)           // Liste geht an keinen Hook
    expect(liest("const M = ['feld'] as const\nuseSprungParameter(M)", 'feld', 'L')).toBe(false)  // fremde Liste
  })
})
