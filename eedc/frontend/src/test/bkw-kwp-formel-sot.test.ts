import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { bkwLeistungKwp } from '../components/forms/sections/investitionFormHelpers'

// Die BKW-Nennleistung (Anzahl × Wp / 1000) stand bis F-32 in ZWEI Kopien —
// `InvestitionForm.tsx` (schreibt die Spalte) und `BalkonkraftwerkFelder.tsx`
// (zeigt den Hinweis) —, und im Einrichtungsassistenten in KEINER: der schrieb
// nur ins `parameter`. Genau daran hing der Fehler: eine reine BKW-Anlage aus
// dem Assistenten bekam auf `/api/solar-prognose` HTTP 400.
//
// ⚠ **Warum dieser Prüfer existiert, ist gemessen, nicht vermutet.** Beim
// Sprengsatz-Durchgang zu F-32 wurde die Formel in `InvestitionForm.tsx` wieder
// inline gelegt UND der Helfer-Import entfernt: `npm run lint` grün, `tsc` grün,
// alle 38 Tests von `forms` + `setup-wizard` grün. Eine dritte Kopie fiel damit
// keinem Prüfer auf — und eine Kopie, die den 0-Fall anders behandelt, schreibt
// beim Leeren eines Feldes still den Altwert fort.
//
// Backend-Pendant der Leserichtung: `test_bkw_wizard_kwp_f32.py` (drei
// Lesestellen auf `get_erzeuger_kwp`).

const SRC = join(process.cwd(), 'src')
const TESTS = join(SRC, 'test')
const SOT = join(SRC, 'components/forms/sections/investitionFormHelpers.ts')

function alleQuelldateien(dir: string): string[] {
  // `src/test` bleibt außen vor: dieser Wächter nennt das Muster selbst.
  if (dir === TESTS) return []
  return readdirSync(dir).flatMap((eintrag) => {
    const pfad = join(dir, eintrag)
    if (statSync(pfad).isDirectory()) return alleQuelldateien(pfad)
    return /\.tsx?$/.test(pfad) && !/\.test\.tsx?$/.test(pfad) ? [pfad] : []
  })
}

/**
 * Rechnet diese Datei die BKW-Nennleistung selbst?
 *
 * ⚠ **Auf DATEI-Ebene, nicht je Zeile — das ist gemessen.** Der erste Entwurf
 * verlangte beides in einer Zeile und blieb beim Sprengsatz stumm: die
 * eingebaute Kopie liest `paramData.leistung_wp` in der einen Zeile und
 * skaliert in der nächsten. Ein Prüfer, der zu eng schaut, ist schlimmer als
 * keiner (die Lehre aus N-264).
 *
 * ⚠ **Wortgrenze ist Absicht:** `modul_leistung_wp` in `PvModulFelder.tsx` ist
 * eine andere Datenrolle (kWp-**Vorschlag** für ein PV-Modul, kein
 * abgeleiteter Spaltenwert) und bleibt hier draußen — sonst wäre die einzige
 * Fundstelle ein Falsch-Positiv und die Liste würde stillschweigend geweitet.
 */
function rechnetSelbst(datei: string): boolean {
  const quelle = readFileSync(datei, 'utf8')
  return /(?<![\w])leistung_wp\b/.test(quelle) && /[*/]\s*1000\b/.test(quelle)
}

describe('BKW-Nennleistung — eine Formel, eine Quelle (F-32)', () => {
  it('rechnet im SoT und liefert `null`, wenn eine Eingabe fehlt', () => {
    expect(bkwLeistungKwp(2, 400)).toBe(0.8)
    expect(bkwLeistungKwp('', 400)).toBeNull()
  })

  it('kein Modul außer dem SoT skaliert `leistung_wp` selbst', () => {
    const fundstellen = alleQuelldateien(SRC)
      .filter((datei) => datei !== SOT && rechnetSelbst(datei))
      .filter((datei) => !readFileSync(datei, 'utf8').includes('bkwLeistungKwp'))
      .map((d) => d.replace(SRC, 'src'))

    expect(fundstellen, [
      'Die BKW-Nennleistung gehört in `bkwLeistungKwp` (Regel 0a: Regel',
      'existiert ⇒ anwenden, keine lokale Formel daneben). Wer hier eine',
      'Fundstelle sieht: Helfer importieren statt Anzahl × Wp / 1000 zu tippen —',
      'sonst behandelt die Kopie den 0-Fall anders und ein geleertes Feld',
      'schreibt still den Altwert fort (F-32).',
    ].join(' ')).toEqual([])
  })

  it('und der SoT selbst trägt die Formel wirklich', () => {
    // Gegenprobe: ohne sie wäre der Test oben auch dann grün, wenn die Formel
    // baumweit verschwunden ist — ein Abwesenheits-Prüfer ohne Anker.
    //
    // ⚠ Sie prüft die **Skalierung**, nicht den Parameter-Schlüssel: der SoT
    // nimmt `leistungWp` (camelCase), der Schlüssel `leistung_wp` gehört den
    // Formularen. Der erste Entwurf dieser Zeile suchte `leistung_wp` auch hier
    // und ging deshalb rot, obwohl der SoT korrekt rechnete — ein Prüfer, der
    // aufs falsche Objekt zeigt.
    const skalierung = readFileSync(SOT, 'utf8')
      .split('\n')
      .filter((z) => /[*/]\s*1000\b/.test(z))
    expect(skalierung.length).toBeGreaterThan(0)
  })
})
