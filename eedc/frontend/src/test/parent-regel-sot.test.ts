import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import {
  PARENT_MAPPING,
  PARENT_REQUIRED,
  parentTypenFuer,
} from '../components/forms/sections/investitionFormHelpers'

// Die Parent-Kind-Regel („welcher Typ darf welchem zugeordnet werden") stand bis
// 2026-07-31 in DREI uneinigen Kopien: hier, in `useSetupWizard.ts` und im
// Backend (`crud.py::get_parent_options`). Nur diese kannte das Balkonkraftwerk
// — der Setup-Wizard bot den BKW-Parent deshalb NIE an, obwohl er der Kanon für
// einen BKW-Akku ist (Zendure, Anker SOLIX). Ein Kanon, den der Einstiegspfad
// nicht anbietet, ist keiner.
//
// Backend-Pendant: `models/investition.py::ERLAUBTE_PARENT_TYPEN`, gepinnt in
// `backend/tests/test_bkw_speicher_datenpfad.py`.

const SRC = join(process.cwd(), 'src')

const TESTS = join(SRC, 'test')

function alleQuelldateien(dir: string): string[] {
  // `src/test` bleibt außen vor: dieser Wächter nennt das gesuchte Symbol
  // selbst und fände sonst sich selbst.
  if (dir === TESTS) return []
  return readdirSync(dir).flatMap((eintrag) => {
    const pfad = join(dir, eintrag)
    if (statSync(pfad).isDirectory()) return alleQuelldateien(pfad)
    return /\.tsx?$/.test(pfad) && !/\.test\.tsx?$/.test(pfad) ? [pfad] : []
  })
}

describe('Parent-Kind-Regel — eine Regel, eine Quelle', () => {
  it('das Balkonkraftwerk ist ein erlaubter Parent für einen Speicher', () => {
    expect(parentTypenFuer('speicher')).toContain('balkonkraftwerk')
    expect(parentTypenFuer('speicher')).toContain('wechselrichter')
  })

  it('die Zuordnung eines Speichers bleibt optional', () => {
    expect(PARENT_REQUIRED).not.toContain('speicher')
    expect(PARENT_REQUIRED).toContain('pv-module')
  })

  // ⚠ Diese Prüfung hieß bis 2026-08-17 „PV-Module hängen weiterhin
  // ausschließlich am Wechselrichter" und pinnte damit eine **Lücke als Regel**:
  // dass ein Balkonkraftwerk keine Module tragen durfte, war der Grund, warum es
  // nur EINE Ausrichtung haben konnte (Melder: Discussion #366, Forum T89667
  // #172). Derselbe Fehlertyp wie die Zeilen-Pinnung aus N-263 — ein Test, der
  // die heutige Implementierung festhält statt ihrer Eigenschaft.
  it('PV-Module hängen an einem Wechselrichter ODER einem Balkonkraftwerk (N-266)', () => {
    expect(parentTypenFuer('pv-module')).toContain('wechselrichter')
    expect(parentTypenFuer('pv-module')).toContain('balkonkraftwerk')
  })

  it('die Zuordnung eines PV-Moduls bleibt Pflicht — auch mit dem BKW als Option', () => {
    // N-266 erweitert die Auswahl, es lockert die Pflicht nicht: ein Modul ohne
    // Träger hätte weder AC-Grenze noch Zuordnungspfad.
    expect(PARENT_REQUIRED).toContain('pv-module')
  })

  it('Typen ohne Parent liefern eine leere Liste, keinen undefined', () => {
    for (const typ of ['wechselrichter', 'e-auto', 'wallbox', 'waermepumpe', 'balkonkraftwerk'] as const) {
      expect(parentTypenFuer(typ)).toEqual([])
    }
  })

  it('PARENT_MAPPING wird genau EINMAL im Baum deklariert', () => {
    const deklarationen = alleQuelldateien(SRC).filter((datei) =>
      /export const PARENT_MAPPING/.test(readFileSync(datei, 'utf8')),
    )
    expect(deklarationen.map((d) => d.replace(SRC, 'src'))).toEqual([
      'src/components/forms/sections/investitionFormHelpers.ts',
    ])
    // Sanity: die SoT selbst ist nicht leer.
    expect(Object.keys(PARENT_MAPPING).length).toBeGreaterThan(0)
  })
})
