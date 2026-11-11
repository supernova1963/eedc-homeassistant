#!/usr/bin/env node
/**
 * check-eine-mechanik.mjs — Wächter W-10 «Eine Mechanik» (Etappe E3 Daten-Checker, Bauplan §4; Konzept §3.1 R6).
 *
 * **Die Regel:** jede Aktion eines Befunds geht über `repairApi.plan` → Vorschau-Kasten → `repairApi.execute`. Die
 * Wrapper-Routen (`/energie-profil/{id}/reaggregate-*`, `kraftstoffpreis-backfill`, `spiegel-abgleich-tag`, die
 * Monatsdaten-Routen `geraetewerte` · `feldwert` · `temperatur-aus-messung`) bleiben für die Werkbank-Direktknöpfe und
 * Skripte; **der Daten-Checker ruft sie nicht** — weder die Seite `pages/DatenCheckerTeile.tsx` noch die Zeile
 * `components/datenchecker/BefundHandgriff.tsx` (seit E5 auch Gruppenzeile, Leiste und `useBefundAktion`). Treffer = 0, sonst rot. Dazu: `window.confirm` kommt dort nicht mehr
 * vor (Konzept §11 Nr. 6 — die Vorschau ersetzt die Rückfrage).
 *
 *   cd eedc/frontend && npm run check:eine-mechanik
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const SRC = join(dirname(fileURLToPath(import.meta.url)), '..', 'src')
// E5: dazu die Gruppenzeile, die Handgriff-Leiste und der geteilte Aktions-Hook.
const DATEIEN = ['pages/DatenCheckerTeile.tsx', 'components/datenchecker/BefundHandgriff.tsx',
  'components/datenchecker/BefundGruppe.tsx', 'components/datenchecker/HandgriffLeiste.tsx',
  'components/datenchecker/useBefundAktion.ts']
/** Direkte Wrapper-Aufrufe und -Pfade (Muster je Zeile, Kommentare ausgenommen). */
const VERBOTEN = [
  /energieProfilApi\s*\./, /monatsdatenApi\s*\./, /repairApi\s*\.\s*(spiegelAbgleichTag|kanalAbgleich)\b/,
  /['"`]\/energie-profil\//, /['"`]\/monatsdaten\//, /window\.confirm\s*\(/,
]

let fehler = 0
for (const rel of DATEIEN) {
  const zeilen = readFileSync(join(SRC, rel), 'utf8').split('\n')
  let imKommentar = false
  zeilen.forEach((z, i) => {
    const t = z.trim()
    if (t.startsWith('/*')) imKommentar = true
    const kommentar = imKommentar || t.startsWith('//') || t.startsWith('*')
    if (t.includes('*/')) imKommentar = false
    if (kommentar) return
    for (const muster of VERBOTEN) {
      if (muster.test(z)) {
        console.error(`${rel}:${i + 1}: ${t}  (Muster ${muster})`)
        fehler += 1
      }
    }
  })
}
if (fehler) {
  console.error(`check:eine-mechanik — ${fehler} direkte(r) Wrapper-Aufruf(e) im Daten-Checker. Aktion über repairApi.plan/execute.`)
  process.exit(1)
}
console.log(`check:eine-mechanik — ${DATEIEN.length} Dateien, 0 direkte Wrapper-Aufrufe.`)
